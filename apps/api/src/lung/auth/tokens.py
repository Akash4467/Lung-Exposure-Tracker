"""Access tokens (short JWTs), refresh tokens (opaque, stored hashed) and email codes."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import jwt

from lung.settings import Settings

ALGORITHM = "HS256"


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class AccessToken:
    token: str
    expires_at: datetime


def create_access_token(user_id: UUID, settings: Settings, now: datetime) -> AccessToken:
    exp = now + timedelta(seconds=settings.access_ttl_s)
    claims = {
        "sub": str(user_id),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": uuid4().hex,
        "typ": "access",
    }
    token = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)
    return AccessToken(token, exp)


LEEWAY_S = 10


def decode_access_token(token: str, settings: Settings, now: datetime) -> UUID:
    """The user id, after checking signature, issuer, audience, type and expiry.

    Expiry is checked against `now` (the app's clock) rather than PyJWT's own, so the
    whole app agrees on the time and expiry can be tested.
    """
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],  # never accept "none" or another algorithm
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={
                "require": ["exp", "iat", "sub", "iss", "aud"],
                "verify_exp": False,
                "verify_iat": False,
            },
        )
        if claims.get("typ") != "access":
            raise InvalidTokenError("not an access token")
        ts = now.timestamp()
        if int(claims["exp"]) + LEEWAY_S < ts:
            raise InvalidTokenError("token expired")
        if int(claims["iat"]) - LEEWAY_S > ts:
            raise InvalidTokenError("token issued in the future")
        return UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as e:
        raise InvalidTokenError(str(e)) from e


def new_refresh_token() -> tuple[str, bytes]:
    """(token for the client, hash to store). 256 bits of randomness."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> bytes:
    # A plain hash is enough: the token is high-entropy, so it can't be guessed from the hash.
    return hashlib.sha256(raw.encode()).digest()


def new_email_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_email_code(code: str, user_id: UUID, purpose: str, settings: Settings) -> bytes:
    """Keyed with the server secret: 6 digits are only a million guesses, so a plain hash of
    the code would be trivial to reverse if the table ever leaked."""
    key = settings.jwt_secret.get_secret_value().encode()
    return hmac.new(key, f"{user_id}:{purpose}:{code}".encode(), hashlib.sha256).digest()
