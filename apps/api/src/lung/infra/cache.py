"""Valkey cache that fails open: if Valkey is down, reads miss and writes are skipped."""

import json
from typing import Any

import structlog
from valkey.asyncio import Valkey
from valkey.exceptions import ValkeyError

log = structlog.get_logger()


class Cache:
    def __init__(self, url: str) -> None:
        self._client = Valkey.from_url(url, socket_timeout=1.0, socket_connect_timeout=1.0)

    async def get_json(self, key: str) -> Any | None:
        try:
            raw = await self._client.get(key)
        except (ValkeyError, OSError):
            log.warning("cache_unavailable", op="get")
            return None
        return None if raw is None else json.loads(raw)

    async def set_json(self, key: str, value: Any, ttl_s: int) -> None:
        try:
            await self._client.set(key, json.dumps(value, default=str), ex=ttl_s)
        except (ValkeyError, OSError):
            log.warning("cache_unavailable", op="set")

    async def claim(self, key: str, ttl_s: int) -> bool:
        """Set the key only if absent. True means "you are first". Fails open (True)."""
        try:
            return bool(await self._client.set(key, "1", ex=ttl_s, nx=True))
        except (ValkeyError, OSError):
            log.warning("cache_unavailable", op="claim")
            return True

    async def hit(self, key: str, window_s: int) -> int | None:
        """Count one hit in a fixed window; returns the count so far, or None if Valkey is
        down (callers then allow the request: rate limits fail open)."""
        try:
            async with self._client.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, window_s, nx=True)
                count, _ = await pipe.execute()
            return int(count)
        except (ValkeyError, OSError):
            log.warning("cache_unavailable", op="hit")
            return None

    async def ttl(self, key: str) -> int:
        try:
            return max(1, int(await self._client.ttl(key)))
        except (ValkeyError, OSError):
            return 60

    async def delete(self, *keys: str) -> None:
        if not keys:
            return
        try:
            await self._client.delete(*keys)
        except (ValkeyError, OSError):
            log.warning("cache_unavailable", op="delete")

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except (ValkeyError, OSError):
            return False

    async def close(self) -> None:
        await self._client.aclose()
