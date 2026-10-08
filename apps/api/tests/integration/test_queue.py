"""The real SQS client against ElasticMQ (`make up`), on a throwaway queue so a running
worker can't steal the messages."""

import uuid

import pytest

from lung.infra.queue import Queue
from lung.settings import Settings

pytestmark = pytest.mark.integration


async def test_send_receive_delete_round_trip() -> None:
    q = Queue(Settings(sqs_endpoint_url="http://localhost:9324"))
    await q.start()
    url = (await q._client.create_queue(QueueName=f"test-{uuid.uuid4().hex[:12]}"))["QueueUrl"]
    try:
        assert await q.ping(url)
        marker = str(uuid.uuid4())
        await q.send(url, {"type": "test", "marker": marker})
        await q.send_many(url, [{"type": "test", "n": i} for i in range(12)])  # 2 batches
        got = []
        for _ in range(10):
            for m in await q.receive(url, wait_s=1, max_messages=10):
                got.append(m.body)
                assert m.receive_count == 1
                await q.delete(url, m)
            if len(got) >= 13:
                break
        assert {"type": "test", "marker": marker} in got
        assert sorted(b["n"] for b in got if "n" in b) == list(range(12))
        assert await q.receive(url, wait_s=0) == []  # all deleted
    finally:
        await q._client.delete_queue(QueueUrl=url)
        await q.close()
