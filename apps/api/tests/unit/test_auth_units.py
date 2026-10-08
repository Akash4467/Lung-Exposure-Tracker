import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from lung.auth import passwords
from lung.auth.tokens import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_email_code,
    hash_refresh_token,
    new_email_code,
    new_refresh_token,
)
from lung.domain.push import Push
from lung.integrations.brevo import BrevoMailer
from lung.integrations.fcm import FcmNotifier
from lung.integrations.google_auth import GoogleVerifier, InvalidGoogleTokenError
from lung.settings import Settings

NOW = datetime(2026, 10, 4, 6, tzinfo=UTC)
S = Settings(jwt_secret="unit-test-secret-that-is-long-enough-123")


# ---------------------------------------------------------------- access tokens


def test_access_token_round_trip() -> None:
    uid = uuid4()
    t = create_access_token(uid, S, NOW)
    assert t.expires_at == NOW + timedelta(minutes=15)
    assert decode_access_token(t.token, S, NOW + timedelta(minutes=14)) == uid


def test_access_token_expires() -> None:
    t = create_access_token(uuid4(), S, NOW)
    with pytest.raises(InvalidTokenError, match="expired"):
        decode_access_token(t.token, S, NOW + timedelta(minutes=16))


@pytest.mark.parametrize(
    "other",
    [
        Settings(jwt_secret="a-different-secret-that-is-long-enough-1"),
        Settings(jwt_secret=S.jwt_secret, jwt_audience="someone-else"),
        Settings(jwt_secret=S.jwt_secret, jwt_issuer="someone-else"),
    ],
)
def test_access_token_rejects_wrong_secret_audience_issuer(other: Settings) -> None:
    t = create_access_token(uuid4(), other, NOW)
    with pytest.raises(InvalidTokenError):
        decode_access_token(t.token, S, NOW)


def test_unsigned_token_is_rejected() -> None:
    claims = {
        "sub": str(uuid4()),
        "iss": S.jwt_issuer,
        "aud": S.jwt_audience,
        "iat": int(NOW.timestamp()),
        "exp": int(NOW.timestamp()) + 900,
        "typ": "access",
    }
    forged = jwt.encode(claims, key=None, algorithm="none")  # type: ignore[arg-type]
    with pytest.raises(InvalidTokenError):
        decode_access_token(forged, S, NOW)


def test_non_access_token_is_rejected() -> None:
    claims = {
        "sub": str(uuid4()),
        "iss": S.jwt_issuer,
        "aud": S.jwt_audience,
        "iat": int(NOW.timestamp()),
        "exp": int(NOW.timestamp()) + 900,
        "typ": "refresh",
    }
    token = jwt.encode(claims, S.jwt_secret.get_secret_value(), algorithm="HS256")
    with pytest.raises(InvalidTokenError, match="not an access token"):
        decode_access_token(token, S, NOW)


# ---------------------------------------------------------------- refresh tokens and codes


def test_refresh_tokens_are_random_and_hashed() -> None:
    raw1, h1 = new_refresh_token()
    raw2, h2 = new_refresh_token()
    assert raw1 != raw2 and len(raw1) >= 43
    assert h1 == hash_refresh_token(raw1) and h1 != h2


def test_email_codes() -> None:
    codes = {new_email_code() for _ in range(200)}
    assert all(len(c) == 6 and c.isdigit() for c in codes) and len(codes) > 150
    u = uuid4()
    a = hash_email_code("123456", u, "verify_email", S)
    assert a == hash_email_code("123456", u, "verify_email", S)
    assert a != hash_email_code("123456", u, "reset_password", S)  # bound to purpose
    assert a != hash_email_code("123456", uuid4(), "verify_email", S)  # and to the user


# ---------------------------------------------------------------- passwords


def test_password_policy() -> None:
    passwords.check_policy("eight ch")
    for bad in ("short", "x" * 129):
        with pytest.raises(passwords.WeakPasswordError):
            passwords.check_policy(bad)
    with pytest.raises(passwords.WeakPasswordError, match="email"):
        passwords.check_policy("Me@Example.com", "me@example.com")


def test_password_hash_and_verify() -> None:
    h = passwords.hash_password("correct horse")
    assert h.startswith("$argon2id$")
    assert passwords.verify_password(h, "correct horse")
    assert not passwords.verify_password(h, "wrong horse")
    assert not passwords.verify_password(None, "anything")  # missing account
    assert not passwords.verify_password("not-a-hash", "anything")


# ---------------------------------------------------------------- Google


@pytest.fixture(scope="module")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _google_token(key: rsa.RSAPrivateKey, **over: Any) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "android-client",
        "sub": "g-1",
        "email": "Ravi@Example.com",
        "email_verified": True,
        "iat": now,
        "exp": now + 600,
    }
    claims.update(over)
    return jwt.encode(claims, key, algorithm="RS256")


def _verifier(key: rsa.RSAPrivateKey) -> GoogleVerifier:
    v = GoogleVerifier(["android-client", "web-client"])
    v._jwks = SimpleNamespace(  # type: ignore[assignment]
        get_signing_key_from_jwt=lambda _t: SimpleNamespace(key=key.public_key())
    )
    return v


async def test_google_valid_token(rsa_key: rsa.RSAPrivateKey) -> None:
    ident = await _verifier(rsa_key).verify(_google_token(rsa_key))
    assert (ident.sub, ident.email, ident.email_verified) == ("g-1", "ravi@example.com", True)


@pytest.mark.parametrize(
    "over",
    [
        {"aud": "someone-else"},
        {"iss": "https://evil.example"},
        {"exp": int(time.time()) - 3600},
        {"email": ""},
    ],
)
async def test_google_rejects_bad_claims(rsa_key: rsa.RSAPrivateKey, over: dict[str, Any]) -> None:
    with pytest.raises(InvalidGoogleTokenError):
        await _verifier(rsa_key).verify(_google_token(rsa_key, **over))


async def test_google_rejects_token_signed_by_another_key(rsa_key: rsa.RSAPrivateKey) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(InvalidGoogleTokenError):
        await _verifier(rsa_key).verify(_google_token(other))


async def test_google_not_configured() -> None:
    with pytest.raises(InvalidGoogleTokenError, match="not configured"):
        await GoogleVerifier([]).verify("x.y.z")


# ---------------------------------------------------------------- Brevo and FCM


async def test_brevo_request_shape() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(201, json={"messageId": "m1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await BrevoMailer(http, "https://api.brevo.test", "k-123", "no-reply@x.in", "Lung").send(
            "a@b.com", "Subj", "Body 123456"
        )
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v3/smtp/email" and seen[0].headers["api-key"] == "k-123"
    assert body["to"] == [{"email": "a@b.com"}] and body["sender"]["email"] == "no-reply@x.in"


async def test_fcm_auth_caching_and_dead_tokens(rsa_key: rsa.RSAPrivateKey) -> None:
    pem = rsa_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    sa = json.dumps(
        {
            "client_email": "svc@proj.iam.gserviceaccount.com",
            "private_key": pem,
            "token_uri": "https://oauth2.test/token",
        }
    )
    token_calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "oauth2.test":
            token_calls.append(req)
            return httpx.Response(200, json={"access_token": "ya29.x", "expires_in": 3600})
        msg = json.loads(req.content)["message"]
        assert req.headers["Authorization"] == "Bearer ya29.x"
        if msg["token"] == "gone":
            return httpx.Response(404, json={"error": {"details": [{"errorCode": "UNREGISTERED"}]}})
        if msg["token"] == "garbled":
            return httpx.Response(
                400, json={"error": {"details": [{"errorCode": "INVALID_ARGUMENT"}]}}
            )
        if msg["token"] == "flaky":
            return httpx.Response(503, json={"error": {}})
        return httpx.Response(200, json={"name": "projects/p/messages/1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        fcm = FcmNotifier(http, "proj", sa)
        push = Push("t", "b", {"screen": "tomorrow"})
        dead = await fcm.send(["ok", "gone", "garbled", "flaky"], push)
        await fcm.send(["ok"], push)
    assert sorted(dead) == ["garbled", "gone"]  # a 503 is not a dead token
    assert len(token_calls) == 1  # OAuth token cached across sends
    assertion = dict(x.split("=") for x in token_calls[0].content.decode().split("&"))["assertion"]
    claims = jwt.decode(
        assertion, rsa_key.public_key(), algorithms=["RS256"], audience="https://oauth2.test/token"
    )
    assert claims["scope"] == "https://www.googleapis.com/auth/firebase.messaging"
