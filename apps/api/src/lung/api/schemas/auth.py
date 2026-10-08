from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import EmailStr, Field

from lung.api.schemas.common import Model

Password = Annotated[str, Field(min_length=1, max_length=256)]
Code = Annotated[str, Field(pattern=r"^\d{6}$", description="6-digit code from the email")]


class RegisterIn(Model):
    email: EmailStr
    password: Password


class LoginIn(Model):
    email: EmailStr
    password: Password


class GoogleIn(Model):
    id_token: Annotated[str, Field(min_length=20, max_length=4096)]


class RefreshIn(Model):
    refresh_token: Annotated[str, Field(min_length=20, max_length=200)]


class CodeIn(Model):
    code: Code


class ForgotIn(Model):
    email: EmailStr


class ResetIn(Model):
    email: EmailStr
    code: Code
    new_password: Password


class ChangePasswordIn(Model):
    current_password: str = Field(default="", max_length=256)  # empty for Google-only accounts
    new_password: Password


class SessionOut(Model):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_at: datetime
    refresh_token: str
    user_id: UUID
    is_new_user: bool


class MeOut(Model):
    user_id: UUID
    email: str | None
    email_verified: bool
    has_password: bool
    google_linked: bool
    onboarded: bool
