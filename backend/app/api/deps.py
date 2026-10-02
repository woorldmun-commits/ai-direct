"""Кто делает запрос и в каком workspace.

actor — только из проверенной сессии: httpOnly cookie → sha256 → sessions (не отозвана, не истекла) → активный
пользователь. Ни тело, ни query, ни заголовки на actor не влияют: других источников пользователя здесь нет.

workspace — из пути, и только через current_workspace: workspace_role(actor, ws) → нет роли → 404 (не 403) →
SET LOCAL app.workspace_id в транзакции запроса (app/tenancy.enter_workspace). Данные workspace читаются только
после этой зависимости; без неё RLS прикладной роли не вернёт ни одной строки."""

import hashlib
import re
from dataclasses import dataclass
from typing import Annotated

import psycopg
from fastapi import Depends, Path, Request

from app.api.db import request_connection
from app.api.errors import ApiError, not_found
from app.tenancy import WorkspaceNotFound, enter_workspace

# Токен сессии — secrets.token_urlsafe(32) (app/auth/login.py): 43 символа base64url. Иное — не наш токен.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{32,128}")
_WS_RE = re.compile(r"ws_([1-9][0-9]{0,18})")
_BIGINT_MAX = 2**63 - 1

Conn = Annotated[psycopg.Connection, Depends(request_connection, scope="function")]


@dataclass(frozen=True)
class Actor:
    user_id: int


@dataclass(frozen=True)
class Workspace:
    id: int
    role: str  # owner · admin · approver · analyst · viewer (workspace_role)
    actor: Actor


def session_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def current_actor(request: Request, conn: Conn) -> Actor:
    token = request.cookies.get(request.app.state.settings.session_cookie)
    if not token or not _TOKEN_RE.fullmatch(token):
        raise ApiError(401, "unauthenticated")
    row = conn.execute("""SELECT s.user_id FROM sessions s JOIN users u ON u.id = s.user_id
                          WHERE s.token_hash = %s AND s.revoked_at IS NULL AND s.expires_at > now()
                            AND u.status = 'active'""", (session_hash(token),)).fetchone()
    if row is None:
        raise ApiError(401, "unauthenticated")  # нет, отозвана, истекла, пользователь деактивирован — одинаково
    return Actor(row[0])


CurrentActor = Annotated[Actor, Depends(current_actor)]


def parse_workspace_id(value: str) -> int | None:
    """Внешний id workspace `ws_<n>` → n; иное — None (для клиента — как несуществующий)."""
    m = _WS_RE.fullmatch(value)
    if not m or int(m.group(1)) > _BIGINT_MAX:
        return None
    return int(m.group(1))


def current_workspace(conn: Conn, actor: CurrentActor,
                      workspace_id: Annotated[str, Path()]) -> Workspace:
    wid = parse_workspace_id(workspace_id)
    if wid is None:
        raise not_found()
    try:
        role = enter_workspace(conn, actor.user_id, wid)
    except WorkspaceNotFound:
        raise not_found() from None
    status = conn.execute("SELECT status FROM workspaces WHERE id = %s", (wid,)).fetchone()
    if status is None:
        raise not_found()  # RLS не показал строку — контекст не тот; ничего не отдаём
    if status[0] == "deletion_pending":
        raise ApiError(410, "workspace_deleted")
    return Workspace(wid, role, actor)


CurrentWorkspace = Annotated[Workspace, Depends(current_workspace)]


def require_manager(ws: Workspace) -> None:
    """Управление командой — только owner / admin организации (API_CONTRACT.md §10)."""
    if ws.role not in ("owner", "admin"):
        raise ApiError(403, "forbidden_role")
