"""Изоляция арендаторов (D13, schema.sql «Изоляция арендаторов»): RLS прикладной роли app_rw пропускает только строки
workspace из app.workspace_id. Не выставлен — 0 строк. Здесь — единственное место, где он выставляется.

API: workspace_role → нет роли — 404 (не 403) → set_local_workspace в транзакции запроса (enter_workspace).
Воркер задачи одного workspace: соединение в autocommit, поэтому SET LOCAL прожил бы один запрос — workspace_scope
выставляет значение на сессию и обязательно сбрасывает его при выходе, чтобы соединение из пула не унесло чужой
workspace в следующую задачу. Системные задачи по многим workspace — роль app_system, без этих функций."""

from contextlib import contextmanager
from typing import Iterator

import psycopg

_KEY = "app.workspace_id"


class WorkspaceNotFound(Exception):
    """Нет доступа к workspace — для пользователя неотличимо от «нет такого» (API: 404)."""


def _id(workspace_id: int) -> str:
    if isinstance(workspace_id, bool) or not isinstance(workspace_id, int) or workspace_id <= 0:
        raise ValueError("workspace_id: нужен положительный int")
    return str(workspace_id)


def set_local_workspace(conn: psycopg.Connection, workspace_id: int) -> None:
    """SET LOCAL app.workspace_id: действует до конца текущей транзакции (запрос API)."""
    if conn.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS:
        raise RuntimeError("set_local_workspace: только внутри транзакции — иначе значение не переживёт запрос")
    conn.execute("SELECT set_config(%s, %s, true)", (_KEY, _id(workspace_id)))


@contextmanager
def workspace_scope(conn: psycopg.Connection, workspace_id: int) -> Iterator[None]:
    """Воркер задачи одного workspace (autocommit): app.workspace_id на сессию, при выходе — прежнее значение.
    Соединение, которое не удалось вернуть в прежнее состояние, закрывается: в пул оно не вернётся."""
    value = _id(workspace_id)
    previous = conn.execute("SELECT current_setting(%s, true)", (_KEY,)).fetchone()[0] or ""
    if previous and previous != value:
        # Задача одного workspace не переходит в другой: такой переход — ошибка кода, а не смена клиента.
        raise RuntimeError("workspace_scope: nested switch to another workspace")
    conn.execute("SELECT set_config(%s, %s, false)", (_KEY, value))
    try:
        yield
    finally:
        try:
            conn.execute("SELECT set_config(%s, %s, false)", (_KEY, previous))
        except psycopg.Error:
            conn.close()
            raise


def task_workspace(conn: psycopg.Connection, kind: str, object_id: int) -> int | None:
    """Workspace задачи по её объекту (sync_run · direct_account · measurement) — до входа в него. None — объекта нет."""
    return conn.execute("SELECT task_workspace(%s, %s)", (kind, object_id)).fetchone()[0]


def workspace_role(conn: psycopg.Connection, user_id: int, workspace_id: int) -> str | None:
    """Эффективная роль: owner · admin · approver · analyst · viewer; None — доступа нет. Одна точка проверки —
    функция workspace_role в БД (представление effective_workspace_access)."""
    return conn.execute("SELECT workspace_role(%s, %s)", (user_id, workspace_id)).fetchone()[0]


def enter_workspace(conn: psycopg.Connection, user_id: int, workspace_id: int) -> str:
    """Запрос API: проверка доступа → SET LOCAL. Вызывать в транзакции запроса. Возвращает роль."""
    role = workspace_role(conn, user_id, workspace_id)
    if role is None:
        raise WorkspaceNotFound(workspace_id)
    set_local_workspace(conn, workspace_id)
    return role
