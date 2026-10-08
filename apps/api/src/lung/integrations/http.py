"""Shared HTTP behaviour for every provider: timeouts and which failures are temporary."""

from typing import Any

import httpx

from lung.domain.errors import Retryable

TEMPORARY_STATUS = {408, 425, 429, 500, 502, 503, 504}


async def request_json(client: httpx.AsyncClient, method: str, url: str, **kw: Any) -> Any:
    try:
        resp = await client.request(method, url, **kw)
    except (httpx.TimeoutException, httpx.TransportError) as e:
        raise Retryable(f"{method} {url}: {type(e).__name__}") from e
    if resp.status_code in TEMPORARY_STATUS:
        raise Retryable(f"{method} {url}: HTTP {resp.status_code}")
    resp.raise_for_status()
    return resp.json()
