"""connection_recheck: путь unavailable → available. Синхронизация недоступный аккаунт не трогает (guard),
а эта задача разрешена и для него — делает один лёгкий авторизованный запрос и обновляет только здоровье.

Запускается, когда пользователь нажал «Проверить доступ» после выдачи прав, и по расписанию для недоступных
аккаунтов. Отозванный токен recheck не лечит: нужен новый OAuth (guard: direct_unavailable / token_revoked)."""

from dataclasses import dataclass
from datetime import datetime

import psycopg

from app.sources.direct import AccountUnavailable, ConnectionUnavailable, DirectSource, RetryLater
from app.worker.guard import Skip, Task, guard, load_state
from app.worker.health import direct_failure, direct_success
from app.worker.locks import workspace_shared
from app.worker.sync import Failed, RetryAt, Skipped


@dataclass(frozen=True)
class Available:
    pass


def _record(conn: psycopg.Connection, ws: int, account: int, now: datetime, error_code: str | None):
    """Под блокировкой и после повторной проверки guard — как запись снимка."""
    with conn.transaction():
        workspace_shared(conn, ws)
        if isinstance(d := guard(Task.RECHECK, load_state(conn, ws, account, now)), Skip):
            return Skipped(d.reason, d.detail)
        if error_code is None:
            direct_success(conn, account, now)
            return Available()
        direct_failure(conn, account, error_code, now)
        return Failed(error_code)


def run_recheck(conn: psycopg.Connection, direct_account_id: int, *, direct: DirectSource,
                now: datetime) -> Available | Skipped | Failed | RetryAt:
    assert conn.autocommit, "воркер требует соединение с autocommit=True"
    row = conn.execute("""SELECT c.workspace_id, coalesce(a.client_login, c.yandex_login)
                          FROM direct_accounts a JOIN direct_connections c ON c.id = a.direct_connection_id
                          WHERE a.id = %s""", (direct_account_id,)).fetchone()
    if row is None:
        return Skipped("account_not_found")
    ws, login = row
    if isinstance(d := guard(Task.RECHECK, load_state(conn, ws, direct_account_id, now)), Skip):
        return Skipped(d.reason, d.detail)
    try:
        direct.check_access(login)  # сеть — без блокировок
    except (AccountUnavailable, ConnectionUnavailable) as e:
        return _record(conn, ws, direct_account_id, now, e.error_code)
    except RetryLater as e:
        return RetryAt(e.retry_in, e.reason)
    return _record(conn, ws, direct_account_id, now, None)
