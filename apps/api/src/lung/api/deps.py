"""Per-request helpers: the app context, the signed-in user, rate limits."""

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from lung.auth.tokens import InvalidTokenError, decode_access_token
from lung.domain.errors import TooManyRequests, Unauthorized
from lung.services.context import AppContext

_bearer = HTTPBearer(auto_error=False)


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx  # type: ignore[no-any-return]


Ctx = Annotated[AppContext, Depends(get_ctx)]


def client_ip(request: Request) -> str:
    # uvicorn --proxy-headers sets this from Caddy's X-Forwarded-For.
    return request.client.host if request.client else "unknown"


async def _limit(ctx: AppContext, key: str, limit: int, window_s: int) -> None:
    count = await ctx.cache.hit(key, window_s)
    if count is not None and count > limit:
        raise TooManyRequests("too many requests; slow down", await ctx.cache.ttl(key))


async def current_user(
    ctx: Ctx,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> UUID:
    """The token's user, after a per-user rate limit (60/min by default)."""
    if creds is None or creds.scheme.lower() != "bearer":
        raise Unauthorized("sign in first", "missing_token")
    try:
        user_id = decode_access_token(creds.credentials, ctx.settings, ctx.clock())
    except InvalidTokenError as e:
        raise Unauthorized("your session has expired; sign in again", "invalid_token") from e
    structlog.contextvars.bind_contextvars(user_id=str(user_id))
    await _limit(ctx, f"rl:user:{user_id}", ctx.settings.rate_limit_per_user_per_min, 60)
    return user_id


UserId = Annotated[UUID, Depends(current_user)]


def ip_limit(bucket: str) -> Callable[[Request, AppContext], Awaitable[None]]:
    """Per-IP limit for unauthenticated endpoints (sign-in, sign-up, password reset)."""

    async def dep(request: Request, ctx: Ctx) -> None:
        await _limit(
            ctx,
            f"rl:ip:{bucket}:{client_ip(request)}",
            ctx.settings.rate_limit_auth_per_ip_per_min,
            60,
        )

    return dep
