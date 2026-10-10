"""Вход через Яндекс ID и сессии (ARCHITECTURE.md §7.1; app/auth/login.py — sign_in).

GET /auth/yandex/authorize?offer=…&pd_consent=…[&marketing=…] → 302 на Яндекс. state (CSRF) и принятые на сайте
версии документов — в httpOnly cookie на время входа: callback сверяет state из query с cookie этого же браузера до
обращения к Яндексу (сверяет sign_in), чужой callback код не обменивает.
GET /auth/yandex/callback → sign_in → cookie сессии → 303 в приложение (ошибка — /login?error=<код>).
POST /auth/logout → 204 · GET /auth/sessions · DELETE /auth/sessions/{id} → 204 (свои; чужая — 404).

Cookie: HttpOnly, Secure, SameSite=Lax (возврат с Яндекса — переход верхнего уровня, Lax его пропускает). Срок
сессии — явный, 30 дней от входа (SESSION_TTL): продлевать нечем — у прикладной роли нет UPDATE на sessions.
id сессии наружу — префикс sha256 от хэша токена: по нему нельзя ни войти, ни найти токен."""

import base64
import binascii
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import Conn, CurrentActor, session_hash
from app.api.errors import ApiError, not_found
from app.api.ratelimit import request_ip
from app.api.serialize import moment
from app.api.services import service
from app.auth.login import LoginError, sign_in
from app.auth.yandex_oauth import OAuthError, authorize_url, new_state
from app.legal.documents import is_published

router = APIRouter()

LOGIN_COOKIE = "oauth_login"
LOGIN_COOKIE_TTL = 600  # секунд на проход через Яндекс
_VERSION = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}(\.[0-9]+)?$"
_SESSION_ID = re.compile(r"ses_([0-9a-f]{24})")
_CODE = re.compile(r"[a-z_0-9]{1,40}")


def set_cookie(response: Response, name: str, value: str, *, max_age: int, path: str = "/") -> None:
    response.set_cookie(name, value, max_age=max_age, path=path, secure=True, httponly=True, samesite="lax")


def clear_cookie(response: Response, name: str, path: str = "/") -> None:
    response.delete_cookie(name, path=path, secure=True, httponly=True, samesite="lax")


def set_session_cookie(request: Request, response: Response, token: str, expires_at: datetime) -> None:
    max_age = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    set_cookie(response, request.app.state.settings.session_cookie, token, max_age=max_age)


def app_redirect(request: Request, path: str, **params) -> RedirectResponse:
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"{request.app.state.settings.app_url}{path}{query}", status_code=303)


class Accepted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offer: Annotated[str | None, Field(pattern=_VERSION)] = None
    pd_consent: Annotated[str | None, Field(pattern=_VERSION)] = None
    marketing: Annotated[str | None, Field(pattern=_VERSION)] = None


def _pack(state: str, accepted: dict) -> str:
    return state + "." + base64.urlsafe_b64encode(json.dumps(accepted).encode()).decode()


def _unpack(value: str | None) -> tuple[str, dict]:
    """cookie → (state, принятые документы); испорченная — пустой state: sign_in ответит state_mismatch."""
    state, _, packed = (value or "").partition(".")
    try:
        accepted = json.loads(base64.urlsafe_b64decode(packed.encode()))
    except (ValueError, binascii.Error):
        return "", {}
    ok = isinstance(accepted, dict) and all(isinstance(v, str) for v in accepted.values())
    return (state, accepted) if ok else ("", {})


@router.get("/auth/yandex/authorize")
def authorize(request: Request, q: Annotated[Accepted, Query()]):
    accepted = {k: v for k, v in q.model_dump().items() if v is not None}
    if not all(is_published(doc, version) for doc, version in accepted.items()):
        raise ApiError(400, "invalid_request", "unknown_document_version")
    state = new_state()
    response = RedirectResponse(authorize_url(service(request, "login_app"), state), status_code=302)
    set_cookie(response, LOGIN_COOKIE, _pack(state, accepted), max_age=LOGIN_COOKIE_TTL, path="/api/v1/auth")
    return response


@router.get("/auth/yandex/callback")
def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    expected, accepted = _unpack(request.cookies.get(LOGIN_COOKIE))
    try:
        if error or not code:
            raise LoginError("access_denied")  # пользователь отказал на странице Яндекса
        with request.app.state.pool.connection() as conn:  # без транзакции до HTTP: sign_in откроет свою
            signed = sign_in(conn, service(request, "http"), service(request, "login_app"), code=code, state=state,
                             expected_state=expected, now=datetime.now(timezone.utc), accepted=accepted,
                             ip=request_ip(request.scope, request.app.state.settings.trusted_proxies),
                             user_agent=request.headers.get("user-agent"))
    except (LoginError, OAuthError) as e:
        response = app_redirect(request, "/login", error=e.code if _CODE.fullmatch(e.code) else "login_failed")
    else:
        response = app_redirect(request, "/")
        set_session_cookie(request, response, signed.session_token, signed.expires_at)
    clear_cookie(response, LOGIN_COOKIE, path="/api/v1/auth")
    return response


@router.post("/auth/logout", status_code=204)
def logout(request: Request, conn: Conn):
    """Без сессии — тоже 204: результат («не вошёл») тот же."""
    name = request.app.state.settings.session_cookie
    token = request.cookies.get(name)
    if token:
        conn.execute("DELETE FROM sessions WHERE token_hash = %s", (session_hash(token),))
    response = Response(status_code=204)
    clear_cookie(response, name)
    return response


def public_id(token_hash: bytes) -> str:
    return "ses_" + hashlib.sha256(token_hash).hexdigest()[:24]


@router.get("/auth/sessions")
def sessions(request: Request, conn: Conn, actor: CurrentActor):
    current = session_hash(request.cookies[request.app.state.settings.session_cookie])
    rows = conn.execute("""SELECT token_hash, created_at, expires_at FROM sessions
                           WHERE user_id = %s AND revoked_at IS NULL AND expires_at > now()
                           ORDER BY created_at DESC""", (actor.user_id,)).fetchall()
    return {"items": [{"id": public_id(bytes(h)), "created_at": moment(c), "expires_at": moment(e),
                       "current": bytes(h) == current} for h, c, e in rows]}


@router.delete("/auth/sessions/{session_id}", status_code=204)
def revoke(conn: Conn, actor: CurrentActor, session_id: str):
    """Отзыв своей сессии (в т. ч. текущей). Чужая или несуществующая — 404."""
    m = _SESSION_ID.fullmatch(session_id)
    if not m:
        raise not_found()
    deleted = conn.execute("""DELETE FROM sessions WHERE user_id = %s
                              AND left(encode(sha256(token_hash), 'hex'), 24) = %s""",
                           (actor.user_id, m.group(1))).rowcount
    if not deleted:
        raise not_found()
    return Response(status_code=204)
