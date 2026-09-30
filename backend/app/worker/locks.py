"""Блокировки workspace (DATA_MODEL.md §9.2) — транзакционные advisory locks PostgreSQL, снимаются на COMMIT/ROLLBACK.

Разделяемая — запись данных (снимок, аудит): синхронизации разных аккаунтов одного workspace идут параллельно.
Исключительная — смена жизненного цикла (деактивация, удаление): ждёт окончания всех записей и не пускает новые.
Сетевые запросы (отчёты Директа, retryIn) выполняются ДО взятия блокировки: долгий отчёт не держит удаление."""

import psycopg

# ponytail: ключ блокировки = workspace_id; другие пространства блокировок — через pg_advisory_xact_lock(int, int).


def workspace_shared(conn: psycopg.Connection, workspace_id: int) -> None:
    conn.execute("SELECT pg_advisory_xact_lock_shared(%s)", (workspace_id,))


def workspace_exclusive(conn: psycopg.Connection, workspace_id: int) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (workspace_id,))


def audit_exclusive(conn: psycopg.Connection, workspace_id: int) -> None:
    """Один аудит на workspace в каждый момент: проблемы и рекомендации пишет только он. Берётся после
    workspace_shared — удаление по-прежнему ждёт аудит, а синхронизации идут параллельно."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('audit:' || %s::text, 0))", (workspace_id,))
