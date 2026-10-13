"""OAuth connects are session/workspace bound, single-use, and never change advertisements."""

from datetime import datetime, timezone
import re
from typing import Annotated

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from app.api.auth_routes import IdleConn
from app.api.deps import Conn, CurrentWorkspace, current_actor, session_hash, require_manager
from app.api.errors import ApiError, not_found
from app.auth.integrations import IntegrationServices
from app.auth.tokens import ConnectionRef, store
from app.auth.yandex_oauth import OAuthError, authorize_url, exchange_code, new_state
from app.sources.metrika import MetrikaUnavailable
from app.tenancy import WorkspaceNotFound, enter_workspace

router = APIRouter()
PROVIDERS = {"yandex_direct": "direct", "yandex_metrika": "metrika"}


def provider_kind(provider):
    if provider not in PROVIDERS:
        raise not_found()
    return PROVIDERS[provider]


def services(request: Request):
    configured = getattr(request.app.state, "integration_services", None)
    if configured is not None:
        return configured
    try:
        configured = IntegrationServices.from_env()
    except (RuntimeError, ValueError, KeyError):
        raise ApiError(503, "provider_not_configured", message="Подключение Яндекса пока не настроено.") from None
    request.app.state.integration_services = configured
    return configured


def enter_manager(conn, actor, workspace):
    try:
        role = enter_workspace(conn, actor, workspace)
    except WorkspaceNotFound:
        raise not_found() from None
    if role not in ("owner", "admin"):
        raise ApiError(403, "forbidden_role")
    status = conn.execute("SELECT status FROM workspaces WHERE id=%s", (workspace,)).fetchone()
    if status is None:
        raise not_found()
    if status[0] == "deletion_pending":
        raise ApiError(410, "workspace_deleted")


def oauth_app(configured, provider):
    try:
        return configured.app_for(provider) if hasattr(configured, "app_for") else configured.app
    except (RuntimeError, ValueError):
        raise ApiError(503, "provider_not_configured", "callback_not_configured") from None


@router.post("/workspaces/{workspace_id}/integrations/{provider}/connect")
def connect(request: Request, conn: Conn, ws: CurrentWorkspace, provider: str):
    provider_kind(provider)
    require_manager(ws)
    configured = services(request)
    app = oauth_app(configured, provider)
    state = new_state()
    token = request.cookies[request.app.state.settings.session_cookie]
    conn.execute(
        "SELECT remember_oauth_state(%s,%s,%s,%s,%s)",
        (ws.actor.user_id, session_hash(token), ws.id, provider, session_hash(state)),
    )
    return {"redirect_url": authorize_url(app, state)}


@router.get("/integrations/{provider}/callback")
def callback(request: Request, conn: IdleConn, provider: str, code: str = "", state: str = ""):
    actor = current_actor(request, conn)
    kind = provider_kind(provider)
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", state) or not code or len(code) > 2048:
        raise ApiError(400, "invalid_request", "state_mismatch")
    configured = services(request)
    app = oauth_app(configured, provider)
    session = session_hash(request.cookies[request.app.state.settings.session_cookie])
    with conn.transaction():
        ws = conn.execute(
            "SELECT claim_oauth_state(%s,%s,%s,%s)", (actor.user_id, session, provider, session_hash(state))
        ).fetchone()[0]
        if ws is None:
            raise ApiError(400, "invalid_request", "state_mismatch")
        enter_manager(conn, actor.user_id, ws)
    try:
        tokens = exchange_code(configured.http, app, code, datetime.now(timezone.utc))
        catalog = configured.discover(provider, tokens.access_token)
    except (OAuthError, MetrikaUnavailable, httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        raise ApiError(
            502, "integration_unavailable", message="Не удалось подключить Яндекс. Повторите подключение."
        ) from None
    with conn.transaction():
        current_actor(request, conn)  # revoked/deactivated during exchange must not connect
        enter_manager(conn, actor.user_id, ws)
        # Whitelisted identifier, never derived from arbitrary input.
        table = f"{kind}_connections"
        conflict = "(workspace_id,yandex_login)" if kind == "direct" else "(workspace_id) WHERE yandex_login IS NULL"
        login = catalog["login"] if kind == "direct" else None
        cid = conn.execute(
            f"""INSERT INTO {table}(workspace_id,yandex_login,scopes,status)
                           VALUES(%s,%s,%s,'disconnected') ON CONFLICT {conflict}
                           DO UPDATE SET scopes=excluded.scopes RETURNING id""",
            (ws, login, list(app.scopes)),
        ).fetchone()[0]
        store(conn, configured.keys, ConnectionRef(kind, ws, cid), tokens)
        if kind == "direct":
            for item in catalog.get("accounts", []):
                conn.execute(
                    """INSERT INTO direct_accounts(direct_connection_id,client_login)
                                  VALUES(%s,%s) ON CONFLICT DO NOTHING""",
                    (cid, item["client_login"]),
                )
        else:
            available = [item["id"] for item in catalog.get("counters", [])]
            if not catalog.get("catalog_truncated", False):
                conn.execute(
                    "UPDATE metrika_counters SET is_selected=false,goal_ids='{}' "
                    "WHERE metrika_connection_id=%s AND NOT(counter_id=ANY(%s))",
                    (cid, available),
                )
            for item in catalog.get("counters", []):
                conn.execute(
                    """INSERT INTO metrika_counters(metrika_connection_id,counter_id)
                                  VALUES(%s,%s) ON CONFLICT DO NOTHING""",
                    (cid, item["id"]),
                )
        conn.execute(
            """INSERT INTO integration_catalogs VALUES(%s,%s,%s,%s,now())
                          ON CONFLICT(workspace_id,provider,connection_id)
                          DO UPDATE SET catalog=excluded.catalog,updated_at=now()""",
            (ws, provider, cid, Jsonb(catalog)),
        )
    return RedirectResponse(f"/app?workspace_id=ws_{ws}", status_code=303)


@router.get("/workspaces/{workspace_id}/integrations")
def integrations(conn: Conn, ws: CurrentWorkspace):
    items = []
    for provider, kind in PROVIDERS.items():
        for cid, status, login in conn.execute(
            f"SELECT id,status,yandex_login FROM {kind}_connections WHERE workspace_id=%s ORDER BY id", (ws.id,)
        ).fetchall():
            item = {"id": f"{kind}_{cid}", "provider": provider, "status": status, "accounts": [], "counters": []}
            cached = conn.execute(
                "SELECT catalog FROM integration_catalogs WHERE workspace_id=%s AND provider=%s AND connection_id=%s",
                (ws.id, provider, cid),
            ).fetchone()
            catalog = cached[0] if cached else {}
            item["catalog_truncated"] = bool(catalog.get("catalog_truncated", False))
            if kind == "direct":
                item["accounts"] = [
                    {"id": f"acc_{aid}", "login": client or login, "is_selected": selected, "status": state}
                    for aid, client, selected, state in conn.execute(
                        "SELECT id,client_login,is_selected,status FROM direct_accounts WHERE direct_connection_id=%s "
                        "ORDER BY id",
                        (cid,),
                    ).fetchall()
                ]
            else:
                metadata = {c["id"]: c for c in catalog.get("counters", [])}
                item["counters"] = [
                    {
                        **metadata.get(counter, {}),
                        "id": f"ctr_{mid}",
                        "counter_id": counter,
                        "is_selected": selected,
                        "goal_ids": goals,
                    }
                    for mid, counter, selected, goals in conn.execute(
                        "SELECT id,counter_id,is_selected,goal_ids FROM metrika_counters "
                        "WHERE metrika_connection_id=%s ORDER BY id",
                        (cid,),
                    ).fetchall()
                ]
            items.append(item)
    return {"items": items}


class AccountSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    is_selected: bool


class CounterSelection(AccountSelection):
    goal_ids: list[Annotated[int, Field(gt=0, le=2**63 - 1)]] = Field(default_factory=list, max_length=10)


def numeric_id(value, prefix):
    if not re.fullmatch(prefix + r"_[1-9][0-9]{0,18}", value):
        raise not_found()
    result = int(value.split("_")[1])
    if result > 2**63 - 1:
        raise not_found()
    return result


@router.put("/workspaces/{workspace_id}/accounts/{account_id}")
def select_account(conn: Conn, ws: CurrentWorkspace, account_id: str, body: AccountSelection):
    require_manager(ws)
    aid = numeric_id(account_id, "acc")
    row = conn.execute(
        "UPDATE direct_accounts SET is_selected=%s WHERE id=%s RETURNING id", (body.is_selected, aid)
    ).fetchone()
    if row is None:
        raise not_found()
    return {"id": account_id, "is_selected": body.is_selected}


@router.put("/workspaces/{workspace_id}/metrika-counters/{counter_id}")
def select_counter(conn: Conn, ws: CurrentWorkspace, counter_id: str, body: CounterSelection):
    require_manager(ws)
    mid = numeric_id(counter_id, "ctr")
    row = conn.execute(
        "SELECT metrika_connection_id,counter_id FROM metrika_counters WHERE id=%s FOR UPDATE", (mid,)
    ).fetchone()
    if row is None:
        raise not_found()
    cid, provider_counter = row
    catalog = conn.execute(
        "SELECT catalog FROM integration_catalogs WHERE workspace_id=%s AND "
        "provider='yandex_metrika' AND connection_id=%s AND updated_at>now()-interval '1 day'",
        (ws.id, cid),
    ).fetchone()
    valid = {
        g["id"]
        for c in (catalog[0].get("counters", []) if catalog else [])
        if c["id"] == provider_counter
        for g in c.get("goals", [])
    }
    if body.is_selected and (
        not body.goal_ids or len(set(body.goal_ids)) != len(body.goal_ids) or not set(body.goal_ids) <= valid
    ):
        raise ApiError(422, "action_unavailable", "goals_not_verified")
    if body.is_selected:
        conn.execute("UPDATE metrika_counters SET is_selected=false WHERE metrika_connection_id=%s", (cid,))
    conn.execute(
        "UPDATE metrika_counters SET is_selected=%s,goal_ids=%s WHERE id=%s",
        (body.is_selected, sorted(body.goal_ids) if body.is_selected else [], mid),
    )
    return {
        "id": counter_id,
        "is_selected": body.is_selected,
        "goal_ids": sorted(body.goal_ids) if body.is_selected else [],
    }
