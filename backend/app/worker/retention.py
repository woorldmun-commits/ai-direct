"""Срок хранения ПД вне workspace — 30 дней: сессии после окончания, email и логин деактивированного пользователя.

Срок хранения текстов поисковых запросов — 60 дней от последнего появления в отчёте (ARCHITECTURE.md §2.4–2.5).

Дата отсечения считается здесь, в часовом поясе данных (даты отчётов Директа — московские), и передаётся в БД явно:
результат не зависит от часового пояса сервера PostgreSQL. Удаление — пачками, каждая в своей транзакции:
задача не держит длинную транзакцию. Снимки и агрегаты stat_rows остаются — удаляется только текст.
Соединение — роль app_deleter: у неё есть только EXECUTE функций удаления."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg

RETENTION_DAYS = 60
PERSONAL_DATA_DAYS = 30
DATA_TIMEZONE = ZoneInfo("Europe/Moscow")
BATCH_SIZE = 5000


def retention_cutoff(now: datetime) -> date:
    """Тексты, последний раз встреченные раньше этой даты, удаляются. Встреченный ровно 60 дней назад — остаётся."""
    if now.tzinfo is None:
        raise ValueError("now: нужна дата с часовым поясом")
    return now.astimezone(DATA_TIMEZONE).date() - timedelta(days=RETENTION_DAYS)


def purge_search_queries(conn: psycopg.Connection, *, cutoff: date, batch_size: int = BATCH_SIZE,
                         max_batches: int | None = None, should_stop=None) -> int:
    """Удаляет все просроченные тексты пачками. Возвращает, сколько удалено. Повторный запуск безопасен (0)."""
    assert conn.autocommit, "каждая пачка — отдельная транзакция: нужен autocommit"
    total = 0
    batches = 0
    while (max_batches is None or batches < max_batches) and not (should_stop and should_stop()):
        deleted = conn.execute("SELECT purge_search_query_texts(%s, %s)", (cutoff, batch_size)).fetchone()[0]
        if not deleted:
            break
        total += deleted
        batches += 1
    return total


def purge_personal_data(conn: psycopg.Connection, *, now: datetime) -> int:
    """Удаляет сессии и обезличивает деактивированных пользователей старше 30 дней. Повторный запуск безопасен (0)."""
    if now.tzinfo is None:
        raise ValueError("now: нужна дата с часовым поясом")
    personal = conn.execute("SELECT purge_personal_data(%s)", (now - timedelta(days=PERSONAL_DATA_DAYS),)).fetchone()[0]
    return personal + conn.execute('SELECT purge_email_reset_mail(%s)', (now,)).fetchone()[0]


def purge_billing_snapshots(conn: psycopg.Connection, *, now: datetime, max_batches: int, should_stop) -> int:
    """Erase request emails after 24h; retain order identity for reconciliation."""
    if now.tzinfo is None:
        raise ValueError('now requires timezone')
    assert conn.autocommit
    total = 0
    for _ in range(max_batches):
        if should_stop():
            break
        deleted = conn.execute('SELECT purge_billing_request_snapshots(%s,%s)',
            (now - timedelta(hours=24), BATCH_SIZE)).fetchone()[0]
        total += deleted
        if deleted < BATCH_SIZE:
            break
    return total
