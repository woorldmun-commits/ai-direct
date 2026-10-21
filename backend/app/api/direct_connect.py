"""Pilot connection: OAuth is bound to the signed-in manager and workspace; tokens stay server-side."""

import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.api.deps import Conn, CurrentActor, CurrentWorkspace, Workspace, require_manager
from app.api.errors import ApiError
from app.api.active import today_msk
from app.auth.tokens import ConnectionRef, store
from app.auth.yandex_oauth import OAuthError, authorize_url, exchange_code, new_state
from app.sources.direct import AccountUnavailable, ConnectionUnavailable, DirectApi, DirectApiError, RetryLater
from app.sources.metrika import MetrikaApi, MetrikaUnavailable
from app.sources.metrika_discovery import parse_goal_list
from app.tenancy import enter_workspace, WorkspaceNotFound
from app.worker.guard import load_state
from app.worker.locks import workspace_exclusive

router = APIRouter()
FLOW_COOKIE = "inrou_direct_flow"
SCOPES = ("direct:api", "metrika:read")


class ConnectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    counter_id: int | None = Field(default=None, gt=0, le=2**63 - 1)
    goal_ids: list[Annotated[int, Field(gt=0, le=2**63 - 1)]] = Field(default_factory=list, max_length=10)
    target_cpa: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)

    @model_validator(mode="after")
    def goals_need_counter(self):
        if bool(self.counter_id) != bool(self.goal_ids) or len(set(self.goal_ids)) != len(self.goal_ids):
            raise ValueError("select a counter and unique goals together")
        return self


class Flow(ConnectInput):
    state: str = Field(min_length=32, max_length=128)
    user_id: int
    workspace_id: int


def _provider(request):
    settings = request.app.state.settings
    if settings.oauth_direct is None or settings.token_keys is None:
        raise ApiError(503, "direct_unavailable", message="Подключение Директа ещё не настроено.")
    return settings.oauth_direct


def _cipher(provider):
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(
        b"inrou:direct-flow:v1\x00" + provider.client_secret.encode()).digest()))


def _access(conn, workspace_id):
    state = load_state(conn, workspace_id, None, datetime.now(timezone.utc))
    if state.workspace_status != 'active' or not state.has_analysis_access:
        raise ApiError(403, "pilot_access_required", message="Администратор должен выдать доступ к пилоту.")


@router.post("/workspaces/{workspace_id}/direct/start")
def start(request: Request, payload: ConnectInput, conn: Conn, ws: CurrentWorkspace):
    require_manager(ws)
    provider = _provider(request)
    _access(conn, ws.id)
    state = new_state()
    flow = Flow(**payload.model_dump(), state=state, user_id=ws.actor.user_id, workspace_id=ws.id)
    response = JSONResponse({"authorize_url": authorize_url(provider, state)})
    response.set_cookie(FLOW_COOKIE, _cipher(provider).encrypt(flow.model_dump_json().encode()).decode(),
                        max_age=600, httponly=True, secure=provider.redirect_uri.startswith("https://"),
                        samesite="lax", path="/")
    return response


def _queue(conn, workspace_id, account_id, counter_id):
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"pilot-sync:{workspace_id}",))
    pending = conn.execute("""SELECT id FROM sync_runs WHERE workspace_id=%s AND direct_account_id=%s
        AND status IN ('queued','running','waiting_report') ORDER BY id LIMIT 1""",
        (workspace_id, account_id)).fetchone()
    if pending:
        return pending[0]
    return conn.execute("""INSERT INTO sync_runs(workspace_id,direct_account_id,metrika_counter_id,kind,
        period_to,runner_managed) VALUES(%s,%s,%s,'resync',%s,true) RETURNING id""",
        (workspace_id, account_id, counter_id, today_msk()-timedelta(days=1))).fetchone()[0]


def _save(conn, request, flow, tokens):
    workspace_exclusive(conn, flow.workspace_id)
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"pilot-sync:{flow.workspace_id}",))
    other = conn.execute("""SELECT 1 FROM direct_connections WHERE workspace_id=%s AND yandex_login<>%s
        AND status<>'disconnected'""", (flow.workspace_id, flow.login)).fetchone()
    if other:
        raise ApiError(409, "pilot_account_limit", message="В пилоте доступен один рекламный кабинет на пространство.")
    busy = conn.execute("""SELECT 1 FROM sync_runs WHERE workspace_id=%s
        AND status IN ('queued','running','waiting_report')""", (flow.workspace_id,)).fetchone()
    if busy:
        raise ApiError(409, "sync_in_progress", message="Дождитесь завершения текущего анализа.")
    keys = request.app.state.settings.token_keys
    connection = conn.execute("""INSERT INTO direct_connections(workspace_id,yandex_login,scopes,status)
        VALUES(%s,%s,%s,'disconnected') ON CONFLICT(workspace_id,yandex_login)
        DO UPDATE SET scopes=EXCLUDED.scopes RETURNING id""", (flow.workspace_id, flow.login, list(SCOPES))).fetchone()[0]
    store(conn, keys, ConnectionRef("direct", flow.workspace_id, connection), tokens)
    account = conn.execute("""INSERT INTO direct_accounts(direct_connection_id,client_login,is_selected)
        VALUES(%s,%s,true) ON CONFLICT(direct_connection_id,(coalesce(client_login,'')))
        DO UPDATE SET is_selected=true,status='active',unavailable_reason=NULL RETURNING id""",
        (connection, flow.login)).fetchone()[0]
    counter = None
    if flow.counter_id:
        mc = conn.execute("""INSERT INTO metrika_connections(workspace_id,yandex_login,scopes,status)
            VALUES(%s,%s,%s,'disconnected') ON CONFLICT(workspace_id,yandex_login)
            DO UPDATE SET scopes=EXCLUDED.scopes RETURNING id""",
            (flow.workspace_id, flow.login, list(SCOPES))).fetchone()[0]
        store(conn, keys, ConnectionRef("metrika", flow.workspace_id, mc), tokens)
        conn.execute("UPDATE metrika_counters SET is_selected=false WHERE metrika_connection_id=%s", (mc,))
        counter = conn.execute("""INSERT INTO metrika_counters(metrika_connection_id,counter_id,goal_ids,is_selected)
            VALUES(%s,%s,%s,true) ON CONFLICT(metrika_connection_id,counter_id)
            DO UPDATE SET goal_ids=EXCLUDED.goal_ids,is_selected=true RETURNING id""",
            (mc, flow.counter_id, flow.goal_ids)).fetchone()[0]
    conn.execute("""INSERT INTO workspace_settings(workspace_id,target_cpa) VALUES(%s,%s)
        ON CONFLICT(workspace_id) DO UPDATE SET target_cpa=EXCLUDED.target_cpa""",
        (flow.workspace_id, flow.target_cpa))
    return _queue(conn, flow.workspace_id, account, counter)


@router.get("/direct/callback")
def callback(request: Request, conn: Conn, actor: CurrentActor,
             state: Annotated[str, Query(min_length=32, max_length=128)] = "",
             code: Annotated[str, Query(max_length=2048)] = "",
             error: Annotated[str, Query(max_length=128)] = ""):
    provider = _provider(request)
    response = RedirectResponse("/workspace?view=integrations&direct=failed", status_code=303)
    response.delete_cookie(FLOW_COOKIE, path="/", httponly=True,
                           secure=provider.redirect_uri.startswith("https://"), samesite="lax")
    try:
        flow = Flow.model_validate_json(_cipher(provider).decrypt(
            request.cookies.get(FLOW_COOKIE, "").encode(), ttl=600))
        if error or not code or actor.user_id != flow.user_id or not hmac.compare_digest(state, flow.state):
            return response
        role = enter_workspace(conn, actor.user_id, flow.workspace_id)
        require_manager(Workspace(flow.workspace_id, role, actor))
        _access(conn, flow.workspace_id)
        slots = request.app.state.auth_callbacks
        if not slots.acquire(blocking=False):
            raise ApiError(503, "auth_busy")
        try:
            with httpx.Client(follow_redirects=False, trust_env=False) as http:
                tokens = exchange_code(http, provider, code, datetime.now(timezone.utc))
                DirectApi(http, tokens.access_token, "connect").check_access(flow.login)
                if flow.counter_id:
                    goals = parse_goal_list(MetrikaApi(http, tokens.access_token).fetch_goals(flow.counter_id))
                    if not set(flow.goal_ids) <= {goal.id for goal in goals}:
                        return response
        finally:
            slots.release()
        _save(conn, request, flow, tokens)
    except (InvalidToken, ValidationError, ValueError, WorkspaceNotFound, OAuthError,
            AccountUnavailable, ConnectionUnavailable, DirectApiError, RetryLater, MetrikaUnavailable, ApiError):
        return response
    response.headers["location"] = f"/workspace?view=integrations&workspace=ws_{flow.workspace_id}&direct=connected"
    return response


@router.get("/workspaces/{workspace_id}/direct")
def status(request: Request, conn: Conn, ws: CurrentWorkspace):
    row = conn.execute("""SELECT r.id,r.status,r.error_code FROM sync_runs r
        WHERE workspace_id=%s AND runner_managed ORDER BY id DESC LIMIT 1""", (ws.id,)).fetchone()
    connected = conn.execute("SELECT 1 FROM direct_connections WHERE workspace_id=%s AND status='connected'",
                             (ws.id,)).fetchone() is not None
    return {"enabled": request.app.state.settings.oauth_direct is not None,
            "manager": ws.role in ("owner", "admin"), "connected": connected,
            "analysis_access": load_state(conn, ws.id, None, datetime.now(timezone.utc)).has_analysis_access,
            "run": {"id": row[0], "status": row[1], "error_code": row[2]} if row else None}


@router.post("/workspaces/{workspace_id}/direct/sync")
def sync(conn: Conn, ws: CurrentWorkspace):
    require_manager(ws)
    _access(conn, ws.id)
    row = conn.execute("""SELECT a.id,(SELECT mc.id FROM metrika_counters mc JOIN metrika_connections m
        ON m.id=mc.metrika_connection_id WHERE m.workspace_id=%s AND m.status='connected'
        AND mc.is_selected ORDER BY mc.id LIMIT 1) FROM direct_accounts a JOIN direct_connections c
        ON c.id=a.direct_connection_id WHERE c.workspace_id=%s AND c.status='connected'
        AND a.is_selected ORDER BY a.id LIMIT 1""", (ws.id, ws.id)).fetchone()
    if not row:
        raise ApiError(409, "direct_not_connected")
    return {"run_id": _queue(conn, ws.id, *row), "status": "queued"}
