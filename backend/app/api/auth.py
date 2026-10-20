"""Browser OAuth boundary; consent travels in an authenticated, ten-minute flow cookie."""

import base64
import hashlib
import hmac
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from typing import Annotated, Literal

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.api.db import request_connection
from app.api.deps import Conn, CurrentActor, session_hash
from app.api.errors import ApiError, error_response
from app.auth.login import DOCUMENTS, LoginError, sign_in
from app.auth.yandex_oauth import OAuthError, authorize_url, new_state
from app.legal.documents import is_published, text_sha256

router = APIRouter(prefix="/auth")
FLOW_COOKIE = "adpilot_oauth_flow"
FLOW_TTL = 600


class LoginStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: dict[str, str] = Field(default_factory=dict, max_length=3)
    locale: Literal["ru-RU"] = "ru-RU"


class LoginFlow(LoginStart):
    state: str = Field(min_length=32, max_length=128)


def _provider(request: Request):
    provider = request.app.state.settings.oauth_login
    if provider is None:
        raise ApiError(503, "auth_unavailable", message="Вход ещё не настроен. Попробуйте позже.")
    return provider


def _cipher(provider) -> Fernet:
    # Domain separation keeps this cookie key independent of the provider credential's other uses.
    key = hashlib.sha256(b"adpilot:oauth-flow:v1\x00" + provider.client_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _secure(request: Request) -> bool:
    return request.app.state.settings.hsts or _provider(request).redirect_uri.startswith("https://")


def _approved(request: Request, payload: LoginStart) -> None:
    if not payload.accepted.keys() <= DOCUMENTS or any(
            not is_published(d, v, payload.locale) for d, v in payload.accepted.items()):
        raise ApiError(400, "invalid_request", reason="terms_not_accepted")
    approvals = request.app.state.settings.signup_approved_hashes
    if any(not hmac.compare_digest(approvals.get(d, ""), text_sha256(d, v, payload.locale))
           for d, v in payload.accepted.items()):
        raise ApiError(503, "legal_unavailable", message="Регистрация откроется после утверждения документов.")


@router.post("/yandex/start")
def start(request: Request, payload: LoginStart):
    provider = _provider(request)
    _approved(request, payload)
    state = new_state()
    flow = LoginFlow(**payload.model_dump(), state=state)
    response = JSONResponse({"authorize_url": authorize_url(provider, state)})
    response.set_cookie(FLOW_COOKIE, _cipher(provider).encrypt(flow.model_dump_json().encode()).decode(),
                        max_age=FLOW_TTL, httponly=True, secure=_secure(request), samesite="lax", path="/")
    return response


@router.get("/yandex/callback")
def callback(request: Request,
             state: Annotated[str, Query(max_length=128)] = "",
             code: Annotated[str, Query(max_length=2048)] = "",
             error: Annotated[str, Query(max_length=128)] = ""):
    provider = _provider(request)
    response = RedirectResponse("/login?error=auth_failed", status_code=303)
    response.delete_cookie(FLOW_COOKIE, path="/", httponly=True, secure=_secure(request), samesite="lax")
    try:
        raw = request.cookies.get(FLOW_COOKIE, "")
        if not raw or len(raw) > 4096 or error or not code:
            return response
        flow = LoginFlow.model_validate_json(_cipher(provider).decrypt(raw.encode(), ttl=FLOW_TTL))
        if not hmac.compare_digest(flow.state.encode(), state.encode()):
            return response
        _approved(request, flow)  # Revoked approvals block an already-started signup too.
        # Verify the unauthenticated flow before borrowing the scarce DB connection.
        # The existing request transaction still encloses sign-in and provisioning.
        with ExitStack() as scope:
            slots = request.app.state.auth_callbacks
            if not slots.acquire(blocking=False):
                return error_response(503, "auth_busy", request.state.request_id, headers={"Retry-After": "1"})
            # Process-local capacity guard; distributed rate limits still belong at the gateway.
            scope.callback(slots.release)
            with contextmanager(request_connection)(request) as conn, \
                    httpx.Client(follow_redirects=False, trust_env=False) as http:
                signed = sign_in(conn, http, provider, code=code, state=state, expected_state=flow.state,
                                 now=datetime.now(timezone.utc), accepted=flow.accepted, locale=flow.locale,
                                 ip=request.client.host if request.client else None,
                                 user_agent=request.headers.get("user-agent"))
                if signed.created:
                    org = conn.execute("SELECT create_organization(%s, 'Моя организация', 'business')",
                                       (signed.user_id,)).fetchone()[0]
                    conn.execute("SELECT create_workspace(%s, %s, 'Мой кабинет')", (signed.user_id, org))
                old_token = request.cookies.get(request.app.state.settings.session_cookie)
                if old_token:
                    conn.execute("DELETE FROM sessions WHERE token_hash = %s", (session_hash(old_token),))
    except (InvalidToken, ValidationError, ValueError, LoginError, OAuthError, ApiError):
        return response
    response.headers["location"] = "/workspace"
    response.set_cookie(request.app.state.settings.session_cookie, signed.session_token, expires=signed.expires_at,
                        httponly=True, secure=_secure(request), samesite="lax", path="/")
    return response


@router.post("/logout")
def logout(request: Request, conn: Conn, actor: CurrentActor):
    conn.execute("DELETE FROM sessions WHERE token_hash = %s AND user_id = %s",
                 (session_hash(request.cookies[request.app.state.settings.session_cookie]), actor.user_id))
    response = JSONResponse({"status": "signed_out"})
    response.delete_cookie(request.app.state.settings.session_cookie, path="/", httponly=True,
                           secure=request.app.state.settings.hsts or request.url.scheme == "https", samesite="lax")
    response.delete_cookie(FLOW_COOKIE, path="/", httponly=True,
                           secure=request.app.state.settings.hsts or request.url.scheme == "https", samesite="lax")
    return response
