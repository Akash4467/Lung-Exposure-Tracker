"""The whole data pipeline: tick → fetch → recompute → scores → alert, with fake providers."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from lung.domain.errors import Retryable
from lung.infra.queue import Message
from lung.repositories import device_tokens as tokens_repo
from lung.repositories import routes as routes_repo
from lung.services import ingest_service, route_service, score_service
from lung.services.context import AppContext
from lung.worker.handlers import HANDLERS
from lung.worker.main import handle

from .conftest import NOW, FakeQueue, FakeRoutes, SpyNotifier, local_today, make_user

pytestmark = pytest.mark.integration


async def _drain(ctx: AppContext, kinds: tuple[str, ...]) -> None:
    """Run queued messages of these kinds until none are left (like the worker would)."""
    q: FakeQueue = ctx.queue  # type: ignore[assignment]
    done = 0
    while done < len(q.sent):
        _, body, _ = q.sent[done]
        done += 1
        if body["type"] in kinds:
            await HANDLERS[body["type"]](ctx, body)


async def _fetch_all(ctx: AppContext) -> None:
    await ingest_service.tick(ctx, NOW)
    await _drain(ctx, ("fetch",))


async def test_tick_fetch_recompute_end_to_end(ctx: AppContext) -> None:
    uid = await make_user(ctx, cooking=True)
    q: FakeQueue = ctx.queue  # type: ignore[assignment]

    assert await ingest_service.tick(ctx, NOW) >= 3  # home, office and the route between
    await _drain(ctx, ("fetch",))
    assert len(q.of_type("recompute")) == 1  # deduplicated across both cells
    assert all(d == 60 for _, b, d in q.sent if b["type"] == "recompute")

    await _drain(ctx, ("recompute",))
    today = await score_service.get_score(ctx, uid, local_today(), is_forecast=False)
    tomorrow = await score_service.get_score(
        ctx, uid, local_today() + timedelta(days=1), is_forecast=True
    )
    assert today is not None and tomorrow is not None
    assert today.band in {"amber", "red"}
    assert today.score_p10 < today.score < today.score_p90
    assert today.indoor_source_share > 0  # cooking counted
    assert today.home_share + today.commute_share + today.office_share == pytest.approx(1)
    assert today.details["tips"], "tips stored"
    assert len(tomorrow.details["hours"]) == 24
    assert tomorrow.fire_risk == "none"
    assert "+" in today.engine_version


async def test_second_fetch_within_the_hour_is_skipped(ctx: AppContext) -> None:
    await make_user(ctx)
    assert await ingest_service.fetch(ctx, "28.6_77.2") > 0
    assert await ingest_service.fetch(ctx, "28.6_77.2") == 0
    assert len(ctx.air.calls) == 1  # type: ignore[attr-defined]


async def test_score_is_cached_after_first_read(ctx: AppContext) -> None:
    uid = await make_user(ctx)
    await _fetch_all(ctx)
    await score_service.recompute(ctx, uid)
    key = score_service.score_cache_key(uid, local_today(), False)
    assert await ctx.cache.get_json(key) is None
    first = await score_service.get_score(ctx, uid, local_today(), False)
    assert await ctx.cache.get_json(key) is not None
    assert await score_service.get_score(ctx, uid, local_today(), False) == first


async def test_recompute_without_air_asks_for_it_and_retries(ctx: AppContext) -> None:
    uid = await make_user(ctx)
    with pytest.raises(Retryable):
        await HANDLERS["recompute"](ctx, {"type": "recompute", "user_id": str(uid)})
    q: FakeQueue = ctx.queue  # type: ignore[assignment]
    forced = q.of_type("fetch")
    assert {"28.6_77.2", "28.5_77.4"} <= {m["cell_id"] for m in forced}
    assert all(m["force"] for m in forced)


async def test_incomplete_profile_is_skipped_quietly(ctx: AppContext) -> None:
    await HANDLERS["recompute"](ctx, {"type": "recompute", "user_id": str(uuid4())})


async def test_day_off_is_all_home(ctx: AppContext) -> None:
    uid = await make_user(ctx, office_days=())
    await _fetch_all(ctx)
    await score_service.recompute(ctx, uid)
    row = await score_service.get_score(ctx, uid, local_today(), False)
    assert row is not None and row.home_share == pytest.approx(1)


async def test_route_straight_line_without_key(ctx: AppContext) -> None:
    uid = await make_user(ctx, route=False)
    assert await route_service.compute_route(ctx, uid) == "straight_line"
    async with ctx.db.session() as s:
        pts = await routes_repo.points(s, uid)
    assert 15 <= len(pts) <= 20
    assert {p.road_class for p in pts} == {"unknown"}


async def test_route_from_provider_feeds_the_score(ctx: AppContext) -> None:
    ctx.routes = FakeRoutes()
    uid = await make_user(ctx, route=False)
    assert await route_service.compute_route(ctx, uid) == "openrouteservice"
    async with ctx.db.session() as s:
        pts = await routes_repo.points(s, uid)
    assert [p.road_class for p in pts] == ["residential", "trunk", "secondary"]
    await _drain(ctx, ("fetch",))  # fetches the route cells
    await score_service.recompute(ctx, uid)
    assert await score_service.get_score(ctx, uid, local_today(), False) is not None


async def test_red_tomorrow_alerts_once(ctx: AppContext) -> None:
    uid = await make_user(ctx)
    async with ctx.db.session() as s:
        await tokens_repo.upsert(s, uid, "tok-1", "android")
        await tokens_repo.upsert(s, uid, "dead-tok", "android")
    await _fetch_all(ctx)
    await HANDLERS["recompute"](ctx, {"type": "recompute", "user_id": str(uid)})

    q: FakeQueue = ctx.queue  # type: ignore[assignment]
    alerts = q.of_type("alert")
    assert [a["alert"] for a in alerts] == ["red_tomorrow"]  # 100-200 µg/m³ all day is red
    await HANDLERS["alert"](ctx, alerts[0])
    await HANDLERS["alert"](ctx, alerts[0])  # SQS redelivery
    spy: SpyNotifier = ctx.notifier  # type: ignore[assignment]
    assert len(spy.sent) == 1
    assert "damaged" not in spy.sent[0][1].body.lower()
    async with ctx.db.session() as s:
        assert await tokens_repo.for_user(s, uid) == ["tok-1"]  # dead token removed


class _RecordingQueue(FakeQueue):
    def __init__(self) -> None:
        super().__init__()
        self.deleted: list[str] = []

    async def delete(self, url: str, msg: Message) -> None:
        self.deleted.append(msg.id)


async def test_worker_deletes_only_after_success(ctx: AppContext) -> None:
    import asyncio

    q = _RecordingQueue()
    ctx.queue = q  # type: ignore[assignment]
    gate = asyncio.Semaphore(2)
    uid = await make_user(ctx)

    ok = Message("m1", "r1", {"type": "fetch", "cell_id": "28.6_77.2"}, 1)
    retry = Message("m2", "r2", {"type": "recompute", "user_id": str(uid)}, 1)  # no air for office
    unknown = Message("m3", "r3", {"type": "nope"}, 1)
    for m in (ok, retry, unknown):
        await handle(ctx, "ingest", m, gate)
    assert q.deleted == ["m1", "m3"]  # m2 stays for a retry


async def test_partitions_function_is_idempotent(ctx: AppContext) -> None:
    async with ctx.db.session() as s:
        await s.execute(text("SELECT ensure_air_partitions(3)"))
        await s.execute(text("SELECT ensure_air_partitions(3)"))
        n = (
            await s.execute(
                text("SELECT count(*) FROM pg_inherits WHERE inhparent = 'air_readings'::regclass")
            )
        ).scalar_one()
    assert n >= 5


async def test_concurrent_fetches_of_one_cell_call_the_provider_once(ctx: AppContext) -> None:
    import asyncio

    await make_user(ctx)
    results = await asyncio.gather(*(ingest_service.fetch(ctx, "28.6_77.2") for _ in range(5)))
    assert sum(1 for r in results if r > 0) == 1
    assert len(ctx.air.calls) == 1  # type: ignore[attr-defined]


async def test_failed_fetch_releases_the_lock(ctx: AppContext) -> None:
    class Boom:
        calls = 0

        async def hourly(self, lat: float, lon: float) -> list:  # type: ignore[type-arg]
            Boom.calls += 1
            raise Retryable("provider down")

    ctx.air = Boom()
    for _ in range(2):
        with pytest.raises(Retryable):
            await ingest_service.fetch(ctx, "28.6_77.2")
    assert Boom.calls == 2  # the second attempt was not blocked by a stale lock


async def test_tick_also_keeps_popular_areas_warm(ctx: AppContext) -> None:
    """A Noida cell gets fetched before anyone lives there, so a new user's score is instant."""
    ctx.settings.warm_areas = True
    q: FakeQueue = ctx.queue  # type: ignore[assignment]
    n = await ingest_service.tick(ctx, NOW)  # no users at all
    fetched = {b["cell_id"] for b in q.of_type("fetch")}
    assert n == len(fetched) > 40
    assert {"28.5_77.3", "28.6_77.2", "19.1_72.9"} <= fetched
    await ingest_service.fetch(ctx, "28.5_77.3")
    assert await ingest_service.fetch(ctx, "28.5_77.3") == 0  # fresh for the hour
