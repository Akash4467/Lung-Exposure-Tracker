"""Transactional email through Brevo's HTTP API (free tier)."""

import httpx

from lung.integrations.http import request_json


class BrevoMailer:
    def __init__(
        self, client: httpx.AsyncClient, base: str, api_key: str, sender: str, sender_name: str
    ) -> None:
        self._client = client
        self._url = f"{base.rstrip('/')}/v3/smtp/email"
        self._key = api_key
        self._sender = {"email": sender, "name": sender_name}

    async def send(self, to: str, subject: str, body: str) -> None:
        await request_json(
            self._client,
            "POST",
            self._url,
            headers={"api-key": self._key, "accept": "application/json"},
            json={
                "sender": self._sender,
                "to": [{"email": to}],
                "subject": subject,
                "textContent": body,
            },
        )
