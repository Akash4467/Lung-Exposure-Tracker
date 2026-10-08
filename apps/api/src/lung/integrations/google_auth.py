"""Verifies Google ID tokens sent by the app after Google sign-in.

Checks the RS256 signature against Google's published keys (cached), the audience (our OAuth
client IDs), the issuer and expiry. No Google client library needed.
"""

import asyncio
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

GOOGLE_CERTS = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ["accounts.google.com", "https://accounts.google.com"]


class InvalidGoogleTokenError(Exception):
    pass


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool


class GoogleVerifier:
    def __init__(self, client_ids: list[str], certs_url: str = GOOGLE_CERTS) -> None:
        self._client_ids = client_ids
        self._jwks = PyJWKClient(certs_url, cache_keys=True, lifespan=6 * 3600)

    def _verify_sync(self, id_token: str) -> GoogleIdentity:
        if not self._client_ids:
            raise InvalidGoogleTokenError("Google sign-in is not configured")
        try:
            key = self._jwks.get_signing_key_from_jwt(id_token).key
            claims = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=self._client_ids,
                issuer=GOOGLE_ISSUERS,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
                leeway=30,
            )
        except jwt.PyJWTError as e:
            raise InvalidGoogleTokenError(str(e)) from e
        if not claims.get("email"):
            raise InvalidGoogleTokenError("token has no email")
        return GoogleIdentity(
            sub=str(claims["sub"]),
            email=str(claims["email"]).lower(),
            email_verified=bool(claims.get("email_verified")),
        )

    async def verify(self, id_token: str) -> GoogleIdentity:
        # PyJWKClient fetches keys with blocking I/O (only when its cache is cold).
        return await asyncio.to_thread(self._verify_sync, id_token)
