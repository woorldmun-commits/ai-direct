"""Эндпоинты фундамента v1.0 — только чтение. Изменений в рекламных кабинетах здесь нет и не будет (v1.1).

GET /health · GET /me · GET /workspaces/{ws}/recommendations · GET /workspaces/{ws}/members (GET …/today — today.py).
Всё, что относится к workspace, читается только через CurrentWorkspace (вход в RLS-контекст)."""

from typing import Annotated

import psycopg
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import Conn, CurrentActor, CurrentWorkspace, require_manager
from app.api.errors import not_found
from app.api.serialize import ext, recommendation_item
from app.tenancy import set_local_workspace

router = APIRouter()


class Strict(BaseModel):
    """Вход API: лишние поля — 400 invalid_request, а не молча проигнорированы."""
    model_config = ConfigDict(extra="forbid")


@router.get("/health")
def health(request: Request):
    """Жив ли процесс и доступна ли БД. Без версий, DSN и деталей ошибок."""
    try:
        with request.app.state.pool.connection(timeout=2) as conn:
            conn.execute("SELECT 1")
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ok"}


@router.get("/me")
def me(conn: Conn, actor: CurrentActor):
    email = conn.execute("SELECT email FROM users WHERE id = %s", (actor.user_id,)).fetchone()[0]
    orgs = conn.execute("""SELECT o.id, o.name, o.kind, m.org_role FROM organization_memberships m
                           JOIN organizations o ON o.id = m.organization_id
                           WHERE m.user_id = %s ORDER BY o.id""", (actor.user_id,)).fetchall()
    # Эффективные роли — user_workspaces (одна точка проверки, effective_workspace_access).
    access = conn.execute("SELECT workspace_id, organization_id, role FROM user_workspaces(%s)",
                          (actor.user_id,)).fetchall()
    by_org: dict[int, list[dict]] = {org_id: [] for org_id, *_ in orgs}
    for ws, org_id, role in access:
        name = _workspace_name(conn, ws)
        if name is None or org_id not in by_org:
            continue
        # owner / admin — полные права по org_role, ws_role: null (API_CONTRACT.md §10)
        by_org[org_id].append({"id": ext("ws", ws), "name": name,
                               "ws_role": None if role in ("owner", "admin") else role})
    return {"user": {"id": ext("u", actor.user_id), "email": email},
            "organizations": [{"id": ext("org", org_id), "name": name, "kind": kind, "org_role": org_role,
                               "workspaces": by_org[org_id]} for org_id, name, kind, org_role in orgs]}


def _workspace_name(conn: psycopg.Connection, ws: int) -> str | None:
    """Название workspace видно только изнутри его контекста (RLS). Доступ уже подтверждён user_workspaces;
    контекст выставляется в savepoint и откатывается — после функции app.workspace_id прежний."""
    with conn.transaction(force_rollback=True):
        set_local_workspace(conn, ws)
        row = conn.execute("SELECT name, status FROM workspaces WHERE id = %s", (ws,)).fetchone()
    if row is None or row[1] == "deletion_pending":
        return None
    return row[0]


class RecommendationsQuery(Strict):
    ad_account: Annotated[str | None, Field(pattern=r"^acc_[1-9][0-9]{0,18}$")] = None
    limit: Annotated[int, Field(ge=1, le=100)] = 50
    cursor: Annotated[str | None, Field(pattern=r"^o[0-9]{1,9}$")] = None


_RECOMMENDATIONS = """
WITH cur AS (
  SELECT r.id, r.created_at, i.direct_account_id, i.object_type, i.object_id,
         coalesce((SELECT e.finding_id FROM recommendation_events e
                   WHERE e.recommendation_id = r.id AND e.type = 'seen_again' ORDER BY e.id DESC LIMIT 1),
                  r.finding_id) AS finding_id,
         (SELECT max(e.created_at) FROM recommendation_events e WHERE e.recommendation_id = r.id) AS last_event_at
  FROM recommendations r JOIN issues i ON i.id = r.issue_id
  WHERE i.workspace_id = %(ws)s AND (%(account)s::bigint IS NULL OR i.direct_account_id = %(account)s::bigint)
)
SELECT cur.id, cur.finding_id, cur.direct_account_id, coalesce(da.client_login, dc.yandex_login),
       cur.object_type, cur.object_id, f.action_level, f.lost, f.recoverable, cur.created_at,
       greatest(cur.created_at, f.created_at, cur.last_event_at)
FROM cur
JOIN findings f ON f.id = cur.finding_id
JOIN direct_accounts da ON da.id = cur.direct_account_id
JOIN direct_connections dc ON dc.id = da.direct_connection_id
ORDER BY (f.lost->>'amount') IS NULL, (f.lost->>'amount')::numeric DESC, cur.id
LIMIT %(limit)s OFFSET %(offset)s
"""


@router.get("/workspaces/{workspace_id}/recommendations")
def recommendations(conn: Conn, ws: CurrentWorkspace, q: Annotated[RecommendationsQuery, Query()]):
    """Список рекомендаций (API_CONTRACT.md §5, минимальный): только поля, которые уже есть в схеме.
    Порядок — по exposure.amount по убыванию, unavailable — в конце. Фильтра по статусу пока нет (см. отчёт)."""
    offset = int(q.cursor[1:]) if q.cursor else 0
    account = int(q.ad_account.removeprefix("acc_")) if q.ad_account else None
    rows = conn.execute(_RECOMMENDATIONS, {"ws": ws.id, "account": account, "limit": q.limit + 1,
                                           "offset": offset}).fetchall()
    more = len(rows) > q.limit
    items = [recommendation_item(*row) for row in rows[:q.limit]]
    return {"items": items, "next_cursor": f"o{offset + q.limit}" if more else None}


@router.get("/workspaces/{workspace_id}/members")
def members(conn: Conn, ws: CurrentWorkspace):
    """Кто имеет доступ к workspace (только чтение; изменение команды — следующие срезы). Смотрят только owner / admin."""
    require_manager(ws)
    rows = conn.execute("""SELECT a.user_id, u.email, a.org_role, a.ws_role FROM effective_workspace_access a
                           JOIN users u ON u.id = a.user_id
                           WHERE a.workspace_id = %s ORDER BY a.user_id""", (ws.id,)).fetchall()
    if not rows:
        raise not_found()  # в своём workspace всегда есть хотя бы owner организации; пусто — контекст не тот
    return {"items": [{"user": {"id": ext("u", user_id), "email": email}, "org_role": org_role,
                       "ws_role": None if org_role in ("owner", "admin") else ws_role}
                      for user_id, email, org_role, ws_role in rows]}

