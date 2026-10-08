"""Push notifications: FCM when configured (integrations/fcm.py), otherwise logged."""

from typing import Protocol

import structlog

from lung.domain.push import Push

log = structlog.get_logger()


__all__ = ["LogNotifier", "Notifier", "Push"]


class Notifier(Protocol):
    async def send(self, tokens: list[str], push: Push) -> list[str]:
        """Send to every token; return the tokens the provider says are dead."""
        ...


class LogNotifier:
    async def send(self, tokens: list[str], push: Push) -> list[str]:
        log.info("push_logged", tokens=len(tokens), title=push.title, data=push.data)
        return []
