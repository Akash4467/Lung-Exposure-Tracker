"""Firebase Cloud Messaging, HTTP v1 API, authenticated with a service-account key.

The service account signs a short JWT; Google exchanges it for an OAuth access token (valid
an hour, cached). Each device token gets its own send; tokens FCM reports as unregistered or
invalid are returned so the caller can delete them.
"""

import asyncio
import json
import time
from typing import Any

import httpx
import jwt
import structlog

from lung.domain.push import Push

log = structlog.get_logger()

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
DEAD_TOKEN_CODES = {"UNREGISTERED", "INVALID_ARGUMENT"}


class FcmNotifier:
    def __init__(
        self, client: httpx.AsyncClient, project_id: str, service_account_json: str
    ) -> None:
        sa: dict[str, Any] = json.loads(service_account_json)
        self._client = client
        self._email = sa["client_email"]
        self._key = sa["private_key"]
        self._token_uri = sa.get("token_uri", "https://oauth2.googleapis.com/token")
        self._send_url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        self._access: tuple[str, float] | None = None
        self._lock = asyncio.Lock()

    async def _access_token(self) -> str:
        async with self._lock:
            if self._access and self._access[1] > time.time() + 60:
                return self._access[0]
            now = int(time.time())
            assertion = jwt.encode(
                {
                    "iss": self._email,
                    "scope": SCOPE,
                    "aud": self._token_uri,
                    "iat": now,
                    "exp": now + 3600,
                },
                self._key,
                algorithm="RS256",
            )
            resp = await self._client.post(
                self._token_uri,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
            resp.raise_for_status()
            body = resp.json()
            self._access = (body["access_token"], now + int(body.get("expires_in", 3600)))
            return self._access[0]

    async def _send_one(self, token: str, push: Push, access: str) -> bool:
        """True if the token is dead."""
        resp = await self._client.post(
            self._send_url,
            headers={"Authorization": f"Bearer {access}"},
            json={
                "message": {
                    "token": token,
                    "notification": {"title": push.title, "body": push.body},
                    "data": push.data,
                    "android": {"priority": "high"},
                }
            },
        )
        if resp.status_code == 200:
            return False
        try:
            details = resp.json().get("error", {}).get("details", [])
            codes = {d.get("errorCode") for d in details}
        except ValueError:
            codes = set()
        if resp.status_code == 404 or codes & DEAD_TOKEN_CODES:
            return True
        log.warning("fcm_send_failed", status=resp.status_code, codes=sorted(c for c in codes if c))
        return False

    async def send(self, tokens: list[str], push: Push) -> list[str]:
        if not tokens:
            return []
        access = await self._access_token()
        dead = await asyncio.gather(*(self._send_one(t, push, access) for t in tokens))
        return [t for t, is_dead in zip(tokens, dead, strict=True) if is_dead]
