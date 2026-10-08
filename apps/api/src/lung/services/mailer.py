"""Email. Brevo in production; without a key, messages are logged (codes included, so a
developer can sign up locally). Never configure LogMailer in production."""

from typing import Protocol

import structlog

log = structlog.get_logger()


class Mailer(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...


class LogMailer:
    async def send(self, to: str, subject: str, body: str) -> None:
        log.info("email_logged", to=to, subject=subject, body=body)


def verification_email(code: str, minutes: int) -> tuple[str, str]:
    return (
        f"{code} is your Lung Exposure Tracker code",
        f"Your verification code is {code}.\n\n"
        f"It expires in {minutes} minutes. If you didn't sign up, you can ignore this email.",
    )


def reset_email(code: str, minutes: int) -> tuple[str, str]:
    return (
        f"{code} is your password reset code",
        f"Use {code} to reset your Lung Exposure Tracker password.\n\n"
        f"It expires in {minutes} minutes. If you didn't ask for this, ignore this email; "
        "your password hasn't changed.",
    )
