"""HTTP SMS authentication. Every provider is injectable; production fails closed."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import Conn, CurrentActor, session_hash
from app.api.errors import ApiError, error_response
from app.auth.phone import CaptchaRequired, PhoneAuthDisabled, RateLimited, request_code
from app.auth.phone_login import SESSION_TTL, sign_in_phone
from app.auth.phone_number import InvalidPhone
from app.auth.providers import PhoneServices, ProviderNotConfigured

router = APIRouter()


def services(request: Request) -> PhoneServices:
    configured = getattr(request.app.state, "phone_services", None)
    if configured is not None:
        return configured
    try:
        configured = PhoneServices.from_env(request.app.state.settings.allowed_origins)
    except (ProviderNotConfigured, RuntimeError, ValueError):
        raise ApiError(503, "provider_not_configured", "phone_auth_disabled", "Вход по SMS пока не настроен.") from None
    request.app.state.phone_services = configured
    return configured


def idle_connection(request: Request):
    with request.app.state.pool.connection() as conn:
        conn.autocommit = True
        try:
            yield conn
        finally:
            conn.autocommit = False


IdleConn = Annotated[object, Depends(idle_connection)]


class CodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str = Field(min_length=8, max_length=32)
    captcha_token: str | None = Field(default=None, max_length=4096)


class CodeVerify(CodeRequest):
    code: str = Field(min_length=1, max_length=16)
    accepted: dict[str, str] = Field(default_factory=dict, max_length=3)


def client_ip(request: Request) -> str:
    # Proxy headers must be validated by the ASGI server's trusted-proxy configuration.
    return request.client.host if request.client else ""


@router.post("/auth/code/request", status_code=202)
def issue_code(request: Request, conn: IdleConn, body: CodeRequest):
    configured = services(request)
    try:
        result = request_code(
            conn,
            config=configured.config,
            sender=configured.sender,
            captcha=configured.captcha,
            phone=body.phone,
            ip=client_ip(request),
            now=datetime.now(timezone.utc),
            captcha_token=body.captcha_token,
        )
    except InvalidPhone:
        raise ApiError(400, "invalid_request", "invalid_phone") from None
    except PhoneAuthDisabled:
        raise ApiError(503, "provider_not_configured", "phone_auth_disabled") from None
    if isinstance(result, RateLimited):
        return error_response(
            429, "rate_limited", request.state.request_id, headers={"Retry-After": str(max(1, result.retry_after))}
        )
    if isinstance(result, CaptchaRequired):
        raise ApiError(422, "action_unavailable", "captcha_required")
    return {"status": "code_requested"}


@router.post("/auth/code/verify")
def verify(request: Request, response: Response, conn: IdleConn, body: CodeVerify):
    result = sign_in_phone(
        conn,
        services(request),
        phone=body.phone,
        code=body.code,
        ip=client_ip(request),
        now=datetime.now(timezone.utc),
        accepted=body.accepted,
        user_agent=request.headers.get("user-agent"),
    )
    if error := result.get("error"):
        status = 422 if error == "acceptance_required" else 401
        raise ApiError(status, error, message="Проверьте код и принятые условия.")
    response.set_cookie(
        request.app.state.settings.session_cookie,
        result["token"],
        max_age=int(SESSION_TTL.total_seconds()),
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )
    email = conn.execute("SELECT email FROM users WHERE id=%s", (result["user_id"],)).fetchone()[0]
    return {"user": {"id": f"u_{result['user_id']}", "phone": result["phone"], "email": email}}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, conn: Conn, actor: CurrentActor):
    token = request.cookies.get(request.app.state.settings.session_cookie, "")
    conn.execute(
        "UPDATE sessions SET revoked_at=now() WHERE token_hash=%s AND user_id=%s", (session_hash(token), actor.user_id)
    )
    response.delete_cookie(
        request.app.state.settings.session_cookie, path="/", secure=True, httponly=True, samesite="lax"
    )


@router.post("/auth/logout-all", status_code=204)
def logout_all(request: Request, response: Response, conn: Conn, actor: CurrentActor):
    conn.execute("UPDATE sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL", (actor.user_id,))
    response.delete_cookie(
        request.app.state.settings.session_cookie, path="/", secure=True, httponly=True, samesite="lax"
    )
