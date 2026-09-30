"""Здоровье подключений — единственное место, где фактический ответ API меняет статус подключения или аккаунта.

connection / account — текущее состояние (status, причина, last_success_at, last_error);
sync_run — история конкретной попытки. Инвариант: успешный авторизованный запрос восстанавливает статус
(connected / active, причина снята, last_success_at = now). Ошибки данных и временные ошибки статус не трогают:
один испорченный отчёт или долгая очередь отчётов не «выключают» рабочий аккаунт."""

from datetime import datetime

import psycopg

from app.sources.direct import ACCOUNT_ERRORS, CONNECTION_ERRORS

_CONNECTION_OF = "SELECT direct_connection_id FROM direct_accounts WHERE id = %s"
LIVE = "status NOT IN ('disconnected', 'token_revoked')"  # подключение, которое пользователь не закрыл


def direct_success(conn: psycopg.Connection, direct_account_id: int, now: datetime) -> None:
    conn.execute("UPDATE direct_accounts SET status = 'active', unavailable_reason = NULL WHERE id = %s",
                 (direct_account_id,))
    conn.execute(f"""UPDATE direct_connections
                     SET status_changed_at = CASE WHEN status <> 'connected' THEN %s ELSE status_changed_at END,
                         status = 'connected', status_detail = NULL, last_success_at = %s
                     WHERE id = ({_CONNECTION_OF}) AND has_token""", (now, now, direct_account_id))


def direct_failure(conn: psycopg.Connection, direct_account_id: int, error_code: str, now: datetime) -> None:
    if error_code in ACCOUNT_ERRORS:
        conn.execute("UPDATE direct_accounts SET status = 'unavailable', unavailable_reason = %s WHERE id = %s",
                     (error_code, direct_account_id))
    elif error_code in CONNECTION_ERRORS:
        if error_code == "token_revoked":
            # отозванный токен хранить нельзя: сбрасывается функцией (шифротекст приложению недоступен);
            # вернуть подключение можно только новым OAuth
            conn.execute(f"""SELECT drop_connection_token('direct', c.workspace_id, c.id, 'token_revoked')
                             FROM direct_connections c WHERE c.id = ({_CONNECTION_OF}) AND c.{LIVE}""",
                         (direct_account_id,))
        else:
            # отключённое пользователем или отозванное подключение ошибка API не «воскрешает» в fixable-статус
            conn.execute(f"""UPDATE direct_connections
                             SET status_changed_at = CASE WHEN status <> %s THEN %s ELSE status_changed_at END,
                                 status = %s
                             WHERE id = ({_CONNECTION_OF}) AND {LIVE}""",
                         (error_code, now, error_code, direct_account_id))
    else:
        return  # формат отчёта, report_timeout — ошибка попытки, не подключения
    conn.execute(f"UPDATE direct_connections SET last_error = %s, last_error_at = %s WHERE id = ({_CONNECTION_OF})",
                 (error_code, now, direct_account_id))


def metrika_result(conn: psycopg.Connection, metrika_counter_id: int, error_code: str | None, now: datetime) -> None:
    """Метрика вызывается при каждой синхронизации со счётчиком, поэтому восстанавливается сама: успех → connected.
    access_denied — подключение (нет прав); counter/goal_not_found — выбор счётчика/целей, статус не меняют."""
    where = "WHERE id = (SELECT metrika_connection_id FROM metrika_counters WHERE id = %s)"
    if error_code is None:
        conn.execute(f"""UPDATE metrika_connections
                         SET status_changed_at = CASE WHEN status <> 'connected' THEN %s ELSE status_changed_at END,
                             status = 'connected', status_detail = NULL, last_success_at = %s
                         {where} AND has_token""", (now, now, metrika_counter_id))
        return
    if error_code == "access_denied":
        conn.execute(f"""UPDATE metrika_connections
                         SET status_changed_at = CASE WHEN status <> 'permission_missing' THEN %s
                                                      ELSE status_changed_at END,
                             status = 'permission_missing'
                         {where} AND {LIVE}""", (now, metrika_counter_id))
    conn.execute(f"UPDATE metrika_connections SET last_error = %s, last_error_at = %s {where}",
                 (error_code, now, metrika_counter_id))
