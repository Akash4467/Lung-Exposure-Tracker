"""Sign-up, sign-in (password or Google), token refresh with rotation, email codes.

Session rules:
- An access token is a 15-minute JWT. A refresh token is an opaque 256-bit string, stored
  only as a hash, valid 30 days, and single-use: every refresh returns a new pair.
- All refresh tokens from one sign-in share a family. If an already-used token comes back,
  someone has a copy, so the whole family is revoked and both parties must sign in again.
- Password reset and password change revoke every session.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from lung.auth import passwords
from lung.auth.tokens import (
    create_access_token,
    hash_email_code,
    hash_refresh_token,
    new_email_code,
    new_refresh_token,
)
from lung.domain.errors import Conflict, InvalidInput, TooManyRequests, Unauthorized
from lung.integrations.google_auth import InvalidGoogleTokenError
from lung.repositories import accounts as accounts_repo
from lung.repositories import email_codes as codes_repo
from lung.repositories import refresh_tokens as refresh_repo
from lung.services.context import AppContext
from lung.services.mailer import reset_email, verification_email

log = structlog.get_logger()

VERIFY, RESET = "verify_email", "reset_password"
LOGIN_FAIL_WINDOW_S = 15 * 60


@dataclass(frozen=True)
class Session:
    user_id: UUID
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    is_new_user: bool = False


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def _issue(
    ctx: AppContext, s: AsyncSession, user_id: UUID, family: UUID | None = None, new: bool = False
) -> Session:
    now = ctx.clock()
    access = create_access_token(user_id, ctx.settings, now)
    raw, digest = new_refresh_token()
    expires = now + timedelta(days=ctx.settings.refresh_ttl_days)
    await refresh_repo.add(s, user_id, family or uuid4(), digest, expires)
    return Session(user_id, access.token, access.expires_at, raw, new)


async def _send_code(ctx: AppContext, user_id: UUID, email: str, purpose: str) -> None:
    code = new_email_code()
    ttl = ctx.settings.email_code_ttl_min
    async with ctx.db.session() as s:
        await codes_repo.put(
            s,
            user_id,
            purpose,
            hash_email_code(code, user_id, purpose, ctx.settings),
            ctx.clock() + timedelta(minutes=ttl),
        )
    subject, body = (verification_email if purpose == VERIFY else reset_email)(code, ttl)
    try:
        await ctx.mailer.send(email, subject, body)
    except Exception:
        # The account still works; the user can ask for another code.
        log.exception("email_send_failed", purpose=purpose)


# ---------------------------------------------------------------- password accounts


async def register(ctx: AppContext, email: str, password: str) -> Session:
    email = normalize_email(email)
    try:
        passwords.check_policy(password, email)
    except passwords.WeakPasswordError as e:
        raise InvalidInput(str(e), "weak_password") from e
    pw_hash = passwords.hash_password(password)
    async with ctx.db.session() as s:
        if await accounts_repo.by_email(s, email):
            raise Conflict("an account with this email already exists", "email_taken")
        user_id = await accounts_repo.create(s, email, pw_hash)
        session = await _issue(ctx, s, user_id, new=True)
    await _send_code(ctx, user_id, email, VERIFY)
    log.info("registered", user_id=str(user_id), method="password")
    return session


async def login(ctx: AppContext, email: str, password: str) -> Session:
    email = normalize_email(email)
    fail_key = f"loginfail:{email}"
    fails = await ctx.cache.get_json(fail_key)
    if fails is not None and int(fails) >= ctx.settings.rate_limit_login_fail_per_email_15min:
        raise TooManyRequests(
            "too many failed sign-ins; try again later", await ctx.cache.ttl(fail_key)
        )

    async with ctx.db.session() as s:
        acct = await accounts_repo.by_email(s, email)
    ok = passwords.verify_password(acct.password_hash if acct else None, password)
    if not ok or acct is None:
        await ctx.cache.hit(fail_key, LOGIN_FAIL_WINDOW_S)
        raise Unauthorized("wrong email or password", "invalid_credentials")

    async with ctx.db.session() as s:
        if acct.password_hash and passwords.needs_rehash(acct.password_hash):
            await accounts_repo.set_password(s, acct.id, passwords.hash_password(password))
        await accounts_repo.touch_login(s, acct.id)
        session = await _issue(ctx, s, acct.id)
    await ctx.cache.delete(fail_key)
    return session


# ---------------------------------------------------------------- Google


async def google_sign_in(ctx: AppContext, id_token: str) -> Session:
    try:
        ident = await ctx.google.verify(id_token)
    except InvalidGoogleTokenError as e:
        raise Unauthorized("Google sign-in failed", "invalid_google_token") from e
    if not ident.email_verified:
        raise Unauthorized("your Google email isn't verified", "google_email_unverified")

    async with ctx.db.session() as s:
        acct = await accounts_repo.by_google_sub(s, ident.sub)
        new = False
        if acct is None:
            acct = await accounts_repo.by_email(s, ident.email)
            if acct is not None:
                # Same email, first Google sign-in: link. Google has proved the address,
                # so an unverified password set by someone else is dropped.
                await accounts_repo.link_google(
                    s, acct.id, ident.sub, drop_password=not acct.email_verified
                )
                user_id = acct.id
            else:
                user_id = await accounts_repo.create(
                    s, ident.email, None, email_verified=True, google_sub=ident.sub
                )
                new = True
        else:
            user_id = acct.id
        await accounts_repo.touch_login(s, user_id)
        session = await _issue(ctx, s, user_id, new=new)
    if new:
        log.info("registered", user_id=str(user_id), method="google")
    return session


# ---------------------------------------------------------------- tokens


async def refresh(ctx: AppContext, raw: str) -> Session:
    digest = hash_refresh_token(raw)
    reused = False
    session: Session | None = None
    async with ctx.db.session() as s:
        row = await refresh_repo.by_hash_for_update(s, digest)
        if row is not None and row.revoked_at is None and row.expires_at > ctx.clock():
            if row.used_at is not None:
                await refresh_repo.revoke_family(s, row.family_id)  # committed below
                reused = True
            else:
                await refresh_repo.mark_used(s, row.id)
                session = await _issue(ctx, s, row.user_id, family=row.family_id)
    if reused:
        log.warning("refresh_token_reuse", user_id=str(row.user_id) if row else None)
    if session is None:
        raise Unauthorized("please sign in again", "invalid_refresh_token")
    return session


async def logout(ctx: AppContext, raw: str) -> None:
    async with ctx.db.session() as s:
        row = await refresh_repo.by_hash_for_update(s, hash_refresh_token(raw))
        if row is not None:
            await refresh_repo.revoke_family(s, row.family_id)


async def logout_everywhere(ctx: AppContext, user_id: UUID) -> None:
    async with ctx.db.session() as s:
        await refresh_repo.revoke_all(s, user_id)


# ---------------------------------------------------------------- email codes


async def resend_verification(ctx: AppContext, user_id: UUID) -> None:
    async with ctx.db.session() as s:
        acct = await accounts_repo.by_id(s, user_id)
    if acct is None or acct.email is None:
        raise Unauthorized("account not found")
    if acct.email_verified:
        return
    await _send_code(ctx, user_id, acct.email, VERIFY)


async def verify_email(ctx: AppContext, user_id: UUID, code: str) -> None:
    digest = hash_email_code(code.strip(), user_id, VERIFY, ctx.settings)
    async with ctx.db.session() as s:
        ok = await codes_repo.consume(s, user_id, VERIFY, digest, ctx.clock())
        if ok:
            await accounts_repo.mark_verified(s, user_id)
    # Raised outside the transaction so the failed attempt is still counted.
    if not ok:
        raise InvalidInput("that code is wrong or has expired", "invalid_code")


async def forgot_password(ctx: AppContext, email: str) -> None:
    """Always succeeds from the caller's point of view, so it can't be used to find out
    which emails have accounts."""
    async with ctx.db.session() as s:
        acct = await accounts_repo.by_email(s, normalize_email(email))
    if acct is not None and acct.email is not None:
        await _send_code(ctx, acct.id, acct.email, RESET)


async def reset_password(ctx: AppContext, email: str, code: str, new_password: str) -> None:
    email = normalize_email(email)
    try:
        passwords.check_policy(new_password, email)
    except passwords.WeakPasswordError as e:
        raise InvalidInput(str(e), "weak_password") from e
    async with ctx.db.session() as s:
        acct = await accounts_repo.by_email(s, email)
        ok = False
        if acct is not None:
            digest = hash_email_code(code.strip(), acct.id, RESET, ctx.settings)
            ok = await codes_repo.consume(s, acct.id, RESET, digest, ctx.clock())
            if ok:
                await accounts_repo.set_password(s, acct.id, passwords.hash_password(new_password))
                # Receiving the code proves the inbox, so the email counts as verified.
                await accounts_repo.mark_verified(s, acct.id)
                await refresh_repo.revoke_all(s, acct.id)
    if not ok:
        raise InvalidInput("that code is wrong or has expired", "invalid_code")


async def change_password(ctx: AppContext, user_id: UUID, current: str, new: str) -> Session:
    async with ctx.db.session() as s:
        acct = await accounts_repo.by_id(s, user_id)
    if acct is None:
        raise Unauthorized("account not found")
    if acct.password_hash and not passwords.verify_password(acct.password_hash, current):
        raise Unauthorized("current password is wrong", "invalid_credentials")
    try:
        passwords.check_policy(new, acct.email)
    except passwords.WeakPasswordError as e:
        raise InvalidInput(str(e), "weak_password") from e
    async with ctx.db.session() as s:
        await accounts_repo.set_password(s, user_id, passwords.hash_password(new))
        await refresh_repo.revoke_all(s, user_id)
        return await _issue(ctx, s, user_id)  # this device stays signed in
