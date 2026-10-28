"""Canonical public SKUs; persisted legacy plan codes remain unchanged."""

PLANS = (
    {'id': 'control', 'name': 'Контроль', 'plan': 'start', 'amount_minor': 299000, 'accounts': 1},
    {'id': 'business', 'name': 'Бизнес', 'plan': 'business', 'amount_minor': 499000, 'accounts': 5},
    {'id': 'agency', 'name': 'Агентство', 'plan': 'business_plus', 'amount_minor': 999000, 'accounts': 15},
)


def account_limit(state):
    if state.paid:
        return next((p['accounts'] for p in PLANS if p['plan'] == state.subscription_plan), 1)
    return 1


def selected_accounts(conn, workspace_id, exclude_login=''):
    return conn.execute('''SELECT count(DISTINCT coalesce(a.client_login,c.yandex_login))
        FROM direct_accounts a JOIN direct_connections c ON c.id=a.direct_connection_id
        WHERE c.workspace_id=%s AND c.status<>'disconnected' AND a.is_selected
        AND coalesce(a.client_login,c.yandex_login)<>%s''', (workspace_id, exclude_login)).fetchone()[0]
