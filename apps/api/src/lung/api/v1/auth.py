from fastapi import APIRouter, Depends, status

from lung.api.deps import Ctx, UserId, ip_limit
from lung.api.schemas.auth import (
    ChangePasswordIn,
    CodeIn,
    ForgotIn,
    GoogleIn,
    LoginIn,
    MeOut,
    RefreshIn,
    RegisterIn,
    ResetIn,
    SessionOut,
)
from lung.services import auth_service, profile_service
from lung.services.auth_service import Session

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _out(s: Session) -> SessionOut:
    return SessionOut(
        access_token=s.access_token,
        expires_at=s.access_expires_at,
        refresh_token=s.refresh_token,
        user_id=s.user_id,
        is_new_user=s.is_new_user,
    )


@router.post("/register", status_code=201, dependencies=[Depends(ip_limit("register"))])
async def register(body: RegisterIn, ctx: Ctx) -> SessionOut:
    """Create an account. A 6-digit verification code is emailed."""
    return _out(await auth_service.register(ctx, body.email, body.password))


@router.post("/login", dependencies=[Depends(ip_limit("login"))])
async def login(body: LoginIn, ctx: Ctx) -> SessionOut:
    return _out(await auth_service.login(ctx, body.email, body.password))


@router.post("/google", dependencies=[Depends(ip_limit("google"))])
async def google(body: GoogleIn, ctx: Ctx) -> SessionOut:
    """Sign in (or up) with the ID token from Google sign-in on the phone."""
    return _out(await auth_service.google_sign_in(ctx, body.id_token))


@router.post("/refresh", dependencies=[Depends(ip_limit("refresh"))])
async def refresh(body: RefreshIn, ctx: Ctx) -> SessionOut:
    """Swap a refresh token for a new pair. Each refresh token works once."""
    return _out(await auth_service.refresh(ctx, body.refresh_token))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshIn, ctx: Ctx) -> None:
    await auth_service.logout(ctx, body.refresh_token)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(user_id: UserId, ctx: Ctx) -> None:
    """Sign out on every device."""
    await auth_service.logout_everywhere(ctx, user_id)


@router.get("/me")
async def me(user_id: UserId, ctx: Ctx) -> MeOut:
    m = await profile_service.me(ctx, user_id)
    return MeOut(**m.__dict__)


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(body: CodeIn, user_id: UserId, ctx: Ctx) -> None:
    await auth_service.verify_email(ctx, user_id, body.code)


@router.post("/verify-email/resend", status_code=status.HTTP_202_ACCEPTED)
async def resend(user_id: UserId, ctx: Ctx) -> None:
    await auth_service.resend_verification(ctx, user_id)


@router.post(
    "/password/forgot",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(ip_limit("forgot"))],
)
async def forgot(body: ForgotIn, ctx: Ctx) -> None:
    """Always 202, whether or not the email has an account."""
    await auth_service.forgot_password(ctx, body.email)


@router.post(
    "/password/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(ip_limit("reset"))],
)
async def reset(body: ResetIn, ctx: Ctx) -> None:
    """Sets the new password and signs out every device."""
    await auth_service.reset_password(ctx, body.email, body.code, body.new_password)


@router.post("/password/change")
async def change_password(body: ChangePasswordIn, user_id: UserId, ctx: Ctx) -> SessionOut:
    """Signs out every other device; returns a fresh session for this one."""
    return _out(
        await auth_service.change_password(ctx, user_id, body.current_password, body.new_password)
    )
