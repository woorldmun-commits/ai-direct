"""Срок хранения текстов поисковых запросов — 60 дней от последнего появления в отчёте (ARCHITECTURE.md §2.4–2.5).

Дата отсечения считается здесь, в часовом поясе данных (даты отчётов Директа — московские), и передаётся в БД явно:
результат не зависит от часового пояса сервера PostgreSQL. Удаление — пачками, каждая в своей транзакции:
задача не держит длинную транзакцию. Снимки и агрегаты stat_rows остаются — удаляется только текст.
Соединение — роль app_deleter: у неё есть только EXECUTE функций удаления."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg

RETENTION_DAYS = 60
DATA_TIMEZONE = ZoneInfo("Europe/Moscow")
BATCH_SIZE = 5000


def retention_cutoff(now: datetime) -> date:
    """Тексты, последний раз встреченные раньше этой даты, удаляются. Встреченный ровно 60 дней назад — остаётся."""
    if now.tzinfo is None:
        raise ValueError("now: нужна дата с часовым поясом")
    return now.astimezone(DATA_TIMEZONE).date() - timedelta(days=RETENTION_DAYS)


def purge_search_queries(conn: psycopg.Connection, *, cutoff: date, batch_size: int = BATCH_SIZE) -> int:
    """Удаляет все просроченные тексты пачками. Возвращает, сколько удалено. Повторный запуск безопасен (0)."""
    assert conn.autocommit, "каждая пачка — отдельная транзакция: нужен autocommit"
    total = 0
    while deleted := conn.execute("SELECT purge_search_query_texts(%s, %s)", (cutoff, batch_size)).fetchone()[0]:
        total += deleted
    return total
