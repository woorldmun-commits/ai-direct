"""Подключения Директа и Метрики (API_CONTRACT.md §8 «Интеграции», ARCHITECTURE.md §7.1). Только чтение кабинетов.

GET  /workspaces/{ws}/integrations                          — статусы подключений и кабинетов (любая роль)
POST /workspaces/{ws}/legal/agency-client-mandate {version} — мандат агентства по клиенту (owner / admin)
POST /workspaces/{ws}/integrations/{provider}/connect       — {redirect_url} на Yandex OAuth (owner / admin)
GET  /integrations/{provider}/callback                      — state → обмен кода → токен в БД → редирект в UI
POST /workspaces/{ws}/integrations/{provider}/disconnect    — токен удаляется, статус disconnected (owner / admin)
GET  /workspaces/{ws}/integrations/yandex_metrika/goals     — счётчики и выбранные цели
PATCH /workspaces/{ws}/integrations/ad-accounts/{id} {selected} — включить / исключить кабинет (owner / admin)

state привязан к workspace, провайдеру и пользователю: всё это — в httpOnly cookie рядом со state. Callback сверяет
state до обращения к Яндексу; HTTP к Яндексу — вне транзакции БД; затем одна транзакция: пользователь сессии = тот,
кто начал подключение → enter_workspace (SET LOCAL) → роль owner/admin → мандат → строка подключения →
set_connection_token (ПОСЛЕ enter_workspace: функция сверяет ws с контекстом). Workspace агентства подключает Директ
только с мандатом (legal_acceptances agency_client_mandate) — иначе 422 acceptance_required.
Логины Яндекса и названия счётчиков в логи не пишутся; токен — только в set_connection_token."""

import hmac
import re
from datetime import datetime, timezone
from typing import Annotated

import psycopg
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import Conn, CurrentWorkspace, current_actor, require_manager
from app.api.errors import ApiError, not_found
from app.api.serialize import ext, moment
from app.api.services import service
from app.api.sessions import app_redirect, clear_cookie, set_cookie
from app.auth.login import LoginError, fetch_user
from app.auth.tokens import ConnectionRef, store
from app.auth.yandex_oauth import OAuthError, authorize_url, exchange_code, new_state
from app.legal.documents import is_published, record_acceptance
from app.sources.metrika import MetrikaApi, MetrikaUnavailable
from app.sources.metrika_discovery import parse_counters
from app.tenancy import WorkspaceNotFound, enter_workspace

router = APIRouter()

KIND = {"yandex_direct": "direct", "yandex_metrika": "metrika"}
TABLE = {"direct": "direct_connections", "metrika": "metrika_connections"}
SCOPE = {"direct": ["direct:api"], "metrika": ["metrika:read"]}
CONNECT_COOKIE = "oauth_connect"
COOKIE_PATH = "/api/v1/integrations"
UI_PATH = "/settings/integrations"


def _kind(provider: str) -> str:
    if provider not in KIND:
        raise not_found()
    return KIND[provider]


def needs_mandate(conn: psycopg.Connection, ws: int) -> bool:
    """Workspace агентства без мандата клиента (D16) — Директ не подключается."""
    kind = conn.execute("""SELECT o.kind FROM workspaces w JOIN organizations o ON o.id = w.organization_id
                           WHERE w.id = %s""", (ws,)).fetchone()[0]
    if kind != "agency":
        return False
    return conn.execute("""SELECT NOT EXISTS (SELECT 1 FROM legal_acceptances WHERE workspace_id = %s
                           AND document = 'agency_client_mandate')""", (ws,)).fetchone()[0]


class Mandate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}(\.[0-9]+)?$")]


@router.post("/workspaces/{workspace_id}/legal/agency-client-mandate", status_code=204)
def mandate(conn: Conn, ws: CurrentWorkspace, body: Mandate, request: Request):
    require_manager(ws)
    if not is_published("agency_client_mandate", body.version):
        raise ApiError(400, "invalid_request", "unknown_document_version")
    try:
        with conn.transaction():
            record_acceptance(conn, user_id=ws.actor.user_id, document="agency_client_mandate", version=body.version,
                              accepted_at=datetime.now(timezone.utc), workspace_id=ws.id,
                              user_agent=request.headers.get("user-agent"))
    except psycopg.errors.IntegrityConstraintViolation:
        raise ApiError(422, "action_unavailable", "not_agency") from None  # триггер check_mandate
    return Response(status_code=204)


@router.post("/workspaces/{workspace_id}/integrations/{provider}/connect")
def connect(request: Request, conn: Conn, ws: CurrentWorkspace, provider: str):
    kind = _kind(provider)
    require_manager(ws)
    if kind == "direct" and needs_mandate(conn, ws.id):
        raise ApiError(422, "acceptance_required", "agency_client_mandate")
    state = new_state()
    response = JSONResponse({"redirect_url": authorize_url(service(request, "api_app"), state)})
    set_cookie(response, CONNECT_COOKIE, f"{state}.{ws.id}.{provider}.{ws.actor.user_id}", max_age=600,
               path=COOKIE_PATH)
    return response


def _cookie(request: Request, provider: str) -> tuple[str, int, int] | None:
    """cookie → (state, ws, user) для этого провайдера; иначе None."""
    parts = (request.cookies.get(CONNECT_COOKIE) or "").split(".")
    if len(parts) != 4 or parts[2] != provider or not (parts[1].isdigit() and parts[3].isdigit()):
        return None
    return parts[0], int(parts[1]), int(parts[3])


def _fetch(request: Request, kind: str, code: str) -> tuple:
    """Обмен кода и чтение, кому выдан токен (и счётчики Метрики) — до транзакции БД."""
    http, app = service(request, "http"), service(request, "api_app")
    tokens = exchange_code(http, app, code, datetime.now(timezone.utc))
    login = fetch_user(http, app, tokens.access_token).login
    counters = ()
    if kind == "metrika":
        try:
            counters = tuple(c.id for c in parse_counters(MetrikaApi(http, tokens.access_token).fetch_counters()))
        except MetrikaUnavailable:
            pass  # счётчики найдёт синхронизация; подключение от этого не ломается
    return tokens, login, counters


def _save(conn: psycopg.Connection, keys, ws: int, kind: str, tokens, login: str, counters: tuple) -> None:
    connection = conn.execute(f"""INSERT INTO {TABLE[kind]} (workspace_id, yandex_login, scopes, status)
                                  VALUES (%s, %s, %s, 'disconnected')
                                  ON CONFLICT (workspace_id, yandex_login) DO UPDATE SET scopes = EXCLUDED.scopes
                                  RETURNING id""", (ws, login, SCOPE[kind])).fetchone()[0]
    store(conn, keys, ConnectionRef(kind, ws, connection), tokens)
    if kind == "metrika":
        for counter in counters:
            conn.execute("""INSERT INTO metrika_counters (metrika_connection_id, counter_id) VALUES (%s, %s)
                            ON CONFLICT DO NOTHING""", (connection, counter))
    elif not _is_agency(conn, ws):  # свой кабинет; клиентов агентства находит AgencyClients.get — его пока нет
        conn.execute("INSERT INTO direct_accounts (direct_connection_id) VALUES (%s) ON CONFLICT DO NOTHING",
                     (connection,))


def _is_agency(conn: psycopg.Connection, ws: int) -> bool:
    return conn.execute("""SELECT o.kind = 'agency' FROM workspaces w JOIN organizations o
                           ON o.id = w.organization_id WHERE w.id = %s""", (ws,)).fetchone()[0]


class _Refused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _authorize_save(request: Request, ws: int, user: int, kind: str, fetched: tuple) -> None:
    with request.app.state.pool.connection() as conn, conn.transaction():
        if current_actor(request, conn).user_id != user:
            raise _Refused("state_mismatch")  # подключение начал другой пользователь
        try:
            role = enter_workspace(conn, user, ws)
        except WorkspaceNotFound:
            raise _Refused("not_found") from None
        if role not in ("owner", "admin"):
            raise _Refused("forbidden_role")
        if kind == "direct" and needs_mandate(conn, ws):
            raise _Refused("acceptance_required")
        _save(conn, service(request, "token_keys"), ws, kind, *fetched)


@router.get("/integrations/{provider}/callback")
def callback(request: Request, provider: str, code: str = "", state: str = "", error: str = ""):
    kind = _kind(provider)
    bound = _cookie(request, provider)
    try:
        if bound is None or not state or not hmac.compare_digest(state.encode(), bound[0].encode()):
            raise _Refused("state_mismatch")  # до обращения к Яндексу
        if error or not code:
            raise _Refused("access_denied")
        _authorize_save(request, bound[1], bound[2], kind, _fetch(request, kind, code))
    except (_Refused, OAuthError, LoginError, ApiError) as e:  # ApiError — нет сессии (unauthenticated)
        response = app_redirect(request, UI_PATH, error=e.code)
    else:
        response = app_redirect(request, UI_PATH, connected=provider)
    clear_cookie(response, CONNECT_COOKIE, path=COOKIE_PATH)
    return response


@router.post("/workspaces/{workspace_id}/integrations/{provider}/disconnect", status_code=204)
def disconnect(conn: Conn, ws: CurrentWorkspace, provider: str):
    kind = _kind(provider)
    require_manager(ws)
    for (connection,) in conn.execute(f"SELECT id FROM {TABLE[kind]} WHERE workspace_id = %s",
                                      (ws.id,)).fetchall():
        conn.execute("SELECT drop_connection_token(%s, %s, %s, 'disconnected')", (kind, ws.id, connection))
    return Response(status_code=204)


@router.get("/workspaces/{workspace_id}/integrations")
def integrations(conn: Conn, ws: CurrentWorkspace):
    items = []
    for provider, kind in KIND.items():
        data_to = conn.execute(f"""SELECT max(period_to) {"FILTER (WHERE 'yandex_metrika' = ANY (sources))"
                                   if kind == "metrika" else ""} FROM snapshots
                                   WHERE workspace_id = %s AND status = 'complete'""", (ws.id,)).fetchone()[0]
        rows = conn.execute(f"""SELECT id, status, yandex_login, last_success_at, last_error FROM {TABLE[kind]}
                                WHERE workspace_id = %s ORDER BY id""", (ws.id,)).fetchall()
        for connection, status, login, last_success, last_error in rows:
            item = {"provider": provider, "status": status, "account": login, "last_success_at": moment(last_success),
                    "data_to": data_to.isoformat() if data_to else None, "error_code": last_error}
            if kind == "direct":
                item["ad_accounts"] = _accounts(conn, connection, login)
            items.append(item)
    return {"items": items}


def _accounts(conn: psycopg.Connection, connection: int, login: str) -> list[dict]:
    rows = conn.execute("""SELECT id, client_login, is_selected, status FROM direct_accounts
                           WHERE direct_connection_id = %s ORDER BY id""", (connection,)).fetchall()
    return [{"id": ext("acc", a), "login": client or login, "selected": sel, "status": st} for a, client, sel, st in rows]


@router.get("/workspaces/{workspace_id}/integrations/yandex_metrika/goals")
def metrika_goals(conn: Conn, ws: CurrentWorkspace):
    """Счётчики и выбранные цели. Ранжированный список целей счётчика (metrika_discovery.suggest_goals) требует
    токена, а роль API токен не читает (только app_token) — его отдаст воркер, когда появится кэш целей."""
    rows = conn.execute("""SELECT c.counter_id, c.is_selected, c.goal_ids FROM metrika_counters c
                           JOIN metrika_connections m ON m.id = c.metrika_connection_id
                           WHERE m.workspace_id = %s ORDER BY c.counter_id""", (ws.id,)).fetchall()
    return {"items": [{"counter_id": str(counter), "selected": selected, "goal_ids": [str(g) for g in goals]}
                      for counter, selected, goals in rows], "candidates": None}


class AccountSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected: bool


@router.patch("/workspaces/{workspace_id}/integrations/ad-accounts/{account_id}")
def select_account(conn: Conn, ws: CurrentWorkspace, account_id: str, body: AccountSelection):
    """API_CONTRACT §8. Чужой кабинет не виден через RLS (direct_accounts → direct_connections текущего workspace) —
    404. Лимит тарифа max_ad_accounts не проверяется: тарифов в схеме ещё нет."""
    require_manager(ws)
    m = re.fullmatch(r"acc_([1-9][0-9]{0,18})", account_id)
    row = m and conn.execute("UPDATE direct_accounts SET is_selected = %s WHERE id = %s RETURNING id",
                             (body.selected, int(m.group(1)))).fetchone()
    if not row:
        raise not_found()
    return {"id": account_id, "selected": body.selected}
