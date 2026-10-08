"""The worker: polls both SQS queues and runs one handler per message.

- A message is deleted only after its handler succeeds.
- `Retryable` leaves the message to reappear after the visibility timeout.
- Any other error is logged; after 5 receives SQS moves the message to the dead-letter queue.
- SIGTERM/SIGINT stop polling, let in-flight jobs finish, then exit.
"""

import asyncio
import contextlib
import os
import signal
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog

from lung.domain.errors import Retryable
from lung.infra.logging import configure_logging
from lung.infra.queue import Message
from lung.services.context import AppContext, build_context, close_context
from lung.settings import Settings, get_settings
from lung.worker.handlers import HANDLERS

log = structlog.get_logger()


async def handle(ctx: AppContext, queue_url: str, msg: Message, gate: asyncio.Semaphore) -> None:
    kind = msg.body.get("type", "?")
    structlog.contextvars.bind_contextvars(msg_id=msg.id, msg_type=kind)
    try:
        handler = HANDLERS.get(kind)
        if handler is None:
            log.error("unknown_message", body=msg.body)
            await ctx.queue.delete(queue_url, msg)  # can never succeed; don't retry
            return
        async with gate:
            await handler(ctx, msg.body)
        await ctx.queue.delete(queue_url, msg)
    except Retryable as e:
        log.warning("job_retry", reason=str(e), receives=msg.receive_count)
    except Exception:
        log.exception("job_failed", receives=msg.receive_count)
    finally:
        structlog.contextvars.unbind_contextvars("msg_id", "msg_type")


HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT_FILE", "/tmp/worker-heartbeat"))  # noqa: S108


def beat() -> None:
    """Touched on every poll; the container health check fails if it goes stale (> 2 min),
    which catches a stuck loop that a plain "process is alive" check would miss."""
    with contextlib.suppress(OSError):
        HEARTBEAT.touch()


async def poll(
    ctx: AppContext, queue_url: str, gate: asyncio.Semaphore, stop: asyncio.Event
) -> None:
    in_flight: set[asyncio.Task[None]] = set()
    while not stop.is_set():
        beat()
        try:
            msgs = await ctx.queue.receive(queue_url, wait_s=10, max_messages=5)
        except Exception:
            log.exception("receive_failed", queue=queue_url)
            await asyncio.sleep(5)
            continue
        for m in msgs:
            task = asyncio.create_task(handle(ctx, queue_url, m, gate))
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)
    if in_flight:
        await asyncio.gather(*in_flight, return_exceptions=True)


async def local_ticker(ctx: AppContext, minutes: int, stop: asyncio.Event) -> None:
    """Local only: stands in for EventBridge Scheduler."""
    while not stop.is_set():
        await ctx.queue.send(
            ctx.settings.sqs_ingest_url, {"type": "tick", "at": datetime.now(UTC).isoformat()}
        )
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=minutes * 60)


async def run(settings: Settings) -> None:
    configure_logging(settings.log_level, json_output=settings.is_production)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):  # Windows has no signal handlers
            loop.add_signal_handler(sig, stop.set)

    async with httpx.AsyncClient(timeout=settings.http_timeout_s) as http:
        ctx = await build_context(settings, http)
        gate = asyncio.Semaphore(settings.worker_concurrency)
        tasks = [
            asyncio.create_task(poll(ctx, settings.sqs_ingest_url, gate, stop)),
            asyncio.create_task(poll(ctx, settings.sqs_user_url, gate, stop)),
        ]
        if settings.local_tick_minutes:
            tasks.append(asyncio.create_task(local_ticker(ctx, settings.local_tick_minutes, stop)))
        log.info("worker_started", concurrency=settings.worker_concurrency)
        try:
            await asyncio.gather(*tasks)
        finally:
            await close_context(ctx)
            log.info("worker_stopped")


def cli() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(get_settings()))
