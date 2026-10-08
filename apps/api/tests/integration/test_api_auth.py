"""Auth over HTTP: register, verify, login, Google, refresh rotation, reset, limits."""

from datetime import timedelta

import httpx
import pytest

from lung.auth.tokens import create_access_token
from lung.services.context import AppContext

from .conftest import NOW, FakeMailer

pytestmark = pytest.mark.integration

PW = "correct horse battery"


async def _register(client: httpx.AsyncClient, email: str = "asha@example.com") -> dict:  # type: ignore[type-arg]
    r = await client.post("/v1/auth/register", json={"email": email, "password": PW})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def _auth(session: dict) -> dict[str, str]:  # type: ignore[type-arg]
    return {"Authorization": f"Bearer {session['access_token']}"}


async def test_register_verify_and_me(client: httpx.AsyncClient, ctx: AppContext) -> None:
    s = await _register(client)
    assert s["is_new_user"] and s["token_type"] == "bearer"

    me = (await client.get("/v1/auth/me", headers=_auth(s))).json()
    assert me["email"] == "asha@example.com"
    assert (me["email_verified"], me["has_password"], me["onboarded"]) == (False, True, False)

    mailer: FakeMailer = ctx.mailer  # type: ignore[assignment]
    code = mailer.last_code("asha@example.com")
    wrong = "000000" if code != "000000" else "111111"
    r = await client.post("/v1/auth/verify-email", json={"code": wrong}, headers=_auth(s))
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_code"
    r = await client.post("/v1/auth/verify-email", json={"code": code}, headers=_auth(s))
    assert r.status_code == 204
    assert (await client.get("/v1/auth/me", headers=_auth(s))).json()["email_verified"]


async def test_register_rejects_duplicates_weak_and_bad_input(client: httpx.AsyncClient) -> None:
    await _register(client)
    r = await client.post("/v1/auth/register", json={"email": "ASHA@example.com ", "password": PW})
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"

    r = await client.post("/v1/auth/register", json={"email": "b@example.com", "password": "short"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "weak_password"

    r = await client.post("/v1/auth/register", json={"email": "not-an-email", "password": PW})
    body = r.json()["error"]
    assert r.status_code == 400 and body["code"] == "validation_failed"
    assert body["details"][0]["field"] == "email"

    r = await client.post(
        "/v1/auth/register", json={"email": "c@example.com", "password": PW, "admin": True}
    )
    assert r.status_code == 400  # unknown fields are rejected


async def test_login_errors_are_identical_for_wrong_password_and_unknown_email(
    client: httpx.AsyncClient,
) -> None:
    await _register(client)
    a = await client.post(
        "/v1/auth/login", json={"email": "asha@example.com", "password": "nope-nope"}
    )
    b = await client.post("/v1/auth/login", json={"email": "ghost@example.com", "password": PW})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()
    ok = await client.post("/v1/auth/login", json={"email": "Asha@Example.com", "password": PW})
    assert ok.status_code == 200


async def test_failed_logins_lock_the_email_for_a_while(client: httpx.AsyncClient) -> None:
    await _register(client)
    for _ in range(5):
        r = await client.post(
            "/v1/auth/login", json={"email": "asha@example.com", "password": "bad-pass"}
        )
        assert r.status_code == 401
    r = await client.post("/v1/auth/login", json={"email": "asha@example.com", "password": PW})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


async def test_ip_rate_limit_on_auth_endpoints(client: httpx.AsyncClient) -> None:
    codes = [
        (
            await client.post("/v1/auth/login", json={"email": f"u{i}@example.com", "password": PW})
        ).status_code
        for i in range(12)
    ]
    assert codes[:10] == [401] * 10
    assert codes[10:] == [429, 429]


async def test_refresh_rotates_and_reuse_kills_the_family(client: httpx.AsyncClient) -> None:
    s1 = await _register(client)
    r = await client.post("/v1/auth/refresh", json={"refresh_token": s1["refresh_token"]})
    assert r.status_code == 200
    s2 = r.json()
    assert s2["refresh_token"] != s1["refresh_token"]

    # The old token comes back: someone has a copy. Both tokens die.
    r = await client.post("/v1/auth/refresh", json={"refresh_token": s1["refresh_token"]})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_refresh_token"
    r = await client.post("/v1/auth/refresh", json={"refresh_token": s2["refresh_token"]})
    assert r.status_code == 401


async def test_logout_revokes_refresh(client: httpx.AsyncClient) -> None:
    s = await _register(client)
    assert (
        await client.post("/v1/auth/logout", json={"refresh_token": s["refresh_token"]})
    ).status_code == 204
    r = await client.post("/v1/auth/refresh", json={"refresh_token": s["refresh_token"]})
    assert r.status_code == 401


async def test_forgot_and_reset_password(client: httpx.AsyncClient, ctx: AppContext) -> None:
    s = await _register(client)
    mailer: FakeMailer = ctx.mailer  # type: ignore[assignment]

    r = await client.post("/v1/auth/password/forgot", json={"email": "nobody@example.com"})
    assert r.status_code == 202
    assert all(to != "nobody@example.com" for to, _, _ in mailer.sent)

    assert (
        await client.post("/v1/auth/password/forgot", json={"email": "asha@example.com"})
    ).status_code == 202
    code = mailer.last_code("asha@example.com")
    new_pw = "a brand new passphrase"
    r = await client.post(
        "/v1/auth/password/reset",
        json={"email": "asha@example.com", "code": code, "new_password": new_pw},
    )
    assert r.status_code == 204
    # Every session is signed out, and only the new password works.
    assert (
        await client.post("/v1/auth/refresh", json={"refresh_token": s["refresh_token"]})
    ).status_code == 401
    assert (
        await client.post("/v1/auth/login", json={"email": "asha@example.com", "password": PW})
    ).status_code == 401
    assert (
        await client.post("/v1/auth/login", json={"email": "asha@example.com", "password": new_pw})
    ).status_code == 200
    # The code is single-use.
    r = await client.post(
        "/v1/auth/password/reset",
        json={"email": "asha@example.com", "code": code, "new_password": "yet another one!"},
    )
    assert r.status_code == 400


async def test_code_dies_after_five_wrong_guesses(
    client: httpx.AsyncClient, ctx: AppContext
) -> None:
    s = await _register(client)
    code = ctx.mailer.last_code("asha@example.com")  # type: ignore[attr-defined]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        await client.post("/v1/auth/verify-email", json={"code": wrong}, headers=_auth(s))
    r = await client.post("/v1/auth/verify-email", json={"code": code}, headers=_auth(s))
    assert r.status_code == 400


async def test_change_password_keeps_this_device_only(client: httpx.AsyncClient) -> None:
    s = await _register(client)
    other = (
        await client.post("/v1/auth/login", json={"email": "asha@example.com", "password": PW})
    ).json()
    r = await client.post(
        "/v1/auth/password/change",
        json={"current_password": PW, "new_password": "changed passphrase"},
        headers=_auth(s),
    )
    assert r.status_code == 200
    mine = r.json()
    assert (
        await client.post("/v1/auth/refresh", json={"refresh_token": other["refresh_token"]})
    ).status_code == 401
    assert (
        await client.post("/v1/auth/refresh", json={"refresh_token": mine["refresh_token"]})
    ).status_code == 200


async def test_google_sign_in_creates_then_reuses_account(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/auth/google", json={"id_token": "google:sub-123:ravi@example.com"})
    assert r.status_code == 200 and r.json()["is_new_user"]
    me = (await client.get("/v1/auth/me", headers=_auth(r.json()))).json()
    assert (me["email_verified"], me["google_linked"], me["has_password"]) == (True, True, False)

    again = await client.post(
        "/v1/auth/google", json={"id_token": "google:sub-123:ravi@example.com"}
    )
    assert again.json()["user_id"] == r.json()["user_id"] and not again.json()["is_new_user"]


async def test_google_takes_over_unverified_email_and_drops_squatters_password(
    client: httpx.AsyncClient,
) -> None:
    squatter = await _register(client, "victim@example.com")  # never verified
    r = await client.post("/v1/auth/google", json={"id_token": "google:sub-9:victim@example.com"})
    assert r.json()["user_id"] == squatter["user_id"]
    r = await client.post("/v1/auth/login", json={"email": "victim@example.com", "password": PW})
    assert r.status_code == 401  # the unproven password no longer works


async def test_google_rejects_bad_or_unverified_tokens(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/auth/google", json={"id_token": "garbage-token-that-is-long"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_google_token"
    r = await client.post("/v1/auth/google", json={"id_token": "google:s:x@example.com:unverified"})
    assert r.json()["error"]["code"] == "google_email_unverified"


async def test_protected_routes_need_a_valid_unexpired_token(
    client: httpx.AsyncClient, ctx: AppContext
) -> None:
    r = await client.get("/v1/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "missing_token"
    assert r.headers["WWW-Authenticate"] == "Bearer"

    s = await _register(client)
    tampered = s["access_token"][:-4] + (
        "AAAA" if not s["access_token"].endswith("AAAA") else "BBBB"
    )
    r = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"

    from uuid import UUID

    old = create_access_token(UUID(s["user_id"]), ctx.settings, NOW - timedelta(hours=1))
    r = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {old.token}"})
    assert r.status_code == 401


async def test_error_envelope_for_unknown_routes(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = await client.get("/v1/auth/login")
    assert r.status_code == 405 and "error" in r.json()
    assert r.headers["X-Request-ID"]
