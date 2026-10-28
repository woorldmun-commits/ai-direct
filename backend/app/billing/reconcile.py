"""Read-only PSP reconciliation. Run daily after configuring the merchant account."""

import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.billing import provider
from app.billing.service import apply_payment, get_order
from app.worker.locks import workspace_exclusive


def reconcile(conn, config):
    rows = conn.execute('''SELECT id,workspace_id,provider_payment_id FROM billing_orders
        WHERE workspace_id IS NOT NULL AND provider_payment_id IS NOT NULL
        AND shop_id=%s AND test=%s ORDER BY created_at''', (config.shop_id, config.test)).fetchall()
    unavailable = 0
    for order_id, workspace_id, payment_id in rows:
        try:
            payment = provider.request(config, 'GET', 'payments/' + payment_id)
            with conn.transaction():
                workspace_exclusive(conn, workspace_id)
                if not conn.execute('SELECT 1 FROM billing_orders WHERE id=%s AND workspace_id=%s',
                                    (order_id, workspace_id)).fetchone():
                    continue
                order = get_order(conn, workspace_id, order_id)
                apply_payment(conn, config, order, payment)
        except provider.ProviderUnavailable:
            unavailable += 1
        except provider.InvalidPayment:
            with conn.transaction():
                conn.execute("UPDATE billing_orders SET status='review_required',provider_body='{}' WHERE id=%s", (order_id,))
    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(Path(__file__).with_name('reconciliation.sql').read_text(encoding='utf-8'))
        drift = cursor.fetchall()
    return {'checked': len(rows), 'unavailable': unavailable, 'issues': drift}


def main():
    config = provider.BillingConfig.from_env(os.environ)
    if config is None:
        raise SystemExit('Billing is disabled; no reconciliation performed')
    with psycopg.connect(os.environ['WORKER_QUEUE_DATABASE_URL'], autocommit=True) as conn:
        if not conn.execute("SELECT current_user='app_system' AND NOT (rolsuper OR rolbypassrls) FROM pg_roles WHERE rolname=current_user").fetchone()[0]:
            raise SystemExit('Billing reconciliation requires app_system')
        result = reconcile(conn, config)
    print(json.dumps(result, default=str))
    raise SystemExit(1 if result['unavailable'] or result['issues'] else 0)


if __name__ == '__main__':
    main()
