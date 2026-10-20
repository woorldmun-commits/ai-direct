"""Тарифные лимиты (решение владельца 2026-10-13). Сколько кабинетов Директа можно включить в анализ: start — 1,
business — 5, business_plus — 25. Без действующей подписки (бесплатный аудит, пробный период, истекла) — как start.
Действующая — та же, что у guard воркера (worker/guard.py): active · past_due · canceled, период идёт сейчас."""

import psycopg

MAX_AD_ACCOUNTS = {"start": 1, "business": 5, "business_plus": 25}


def current_plan(conn: psycopg.Connection, ws: int) -> str:
    row = conn.execute("""SELECT plan FROM subscriptions WHERE workspace_id = %s
                          AND status IN ('active', 'past_due', 'canceled')
                          AND current_period_start <= now() AND current_period_end > now()
                          ORDER BY current_period_end DESC, id DESC LIMIT 1""", (ws,)).fetchone()
    return row[0] if row else "start"


def ad_accounts_left(conn: psycopg.Connection, ws: int, except_account: int) -> int:
    """Сколько ещё кабинетов можно выбрать, не считая except_account (повторный выбор того же — не новый)."""
    selected = conn.execute("""SELECT count(*) FROM direct_accounts da
                               JOIN direct_connections dc ON dc.id = da.direct_connection_id
                               WHERE dc.workspace_id = %s AND da.is_selected AND da.id <> %s""",
                            (ws, except_account)).fetchone()[0]
    return MAX_AD_ACCOUNTS[current_plan(conn, ws)] - selected
