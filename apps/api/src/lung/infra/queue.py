"""SQS (ElasticMQ locally). Messages are small JSON with ids only."""

import json
from collections.abc import Mapping
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

import aioboto3

from lung.settings import Settings


@dataclass(frozen=True)
class Message:
    id: str
    receipt: str
    body: dict[str, Any]
    receive_count: int


class Queue:
    """One SQS client shared by every queue URL."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stack = AsyncExitStack()
        self._client: Any = None

    async def start(self) -> None:
        session = aioboto3.Session()
        self._client = await self._stack.enter_async_context(
            session.client(
                "sqs",
                region_name=self._settings.aws_region,
                endpoint_url=self._settings.sqs_endpoint_url,
            )
        )

    async def close(self) -> None:
        await self._stack.aclose()

    async def send(self, queue_url: str, body: Mapping[str, Any], delay_s: int = 0) -> None:
        await self._client.send_message(
            QueueUrl=queue_url, MessageBody=json.dumps(body), DelaySeconds=delay_s
        )

    async def send_many(self, queue_url: str, bodies: list[Mapping[str, Any]]) -> None:
        for i in range(0, len(bodies), 10):  # SQS batch limit
            entries = [
                {"Id": str(n), "MessageBody": json.dumps(b)}
                for n, b in enumerate(bodies[i : i + 10])
            ]
            await self._client.send_message_batch(QueueUrl=queue_url, Entries=entries)

    async def receive(
        self, queue_url: str, wait_s: int = 20, max_messages: int = 5
    ) -> list[Message]:
        resp = await self._client.receive_message(
            QueueUrl=queue_url,
            WaitTimeSeconds=wait_s,
            MaxNumberOfMessages=max_messages,
            MessageSystemAttributeNames=["ApproximateReceiveCount"],
        )
        return [
            Message(
                id=m["MessageId"],
                receipt=m["ReceiptHandle"],
                body=json.loads(m["Body"]),
                receive_count=int(m.get("Attributes", {}).get("ApproximateReceiveCount", 1)),
            )
            for m in resp.get("Messages", [])
        ]

    async def delete(self, queue_url: str, msg: Message) -> None:
        await self._client.delete_message(QueueUrl=queue_url, ReceiptHandle=msg.receipt)

    async def ping(self, queue_url: str) -> bool:
        try:
            await self._client.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])
        except Exception:
            return False
        return True
