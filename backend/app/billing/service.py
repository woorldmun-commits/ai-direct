"""Durable orders; fulfillment and its deduplication marker share one transaction."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parseaddr

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.api.errors import ApiError
from app.worker.guard import load_state
from app.worker.locks import workspace_exclusive
from app.billing.catalog import PLANS
from app.billing.provider import InvalidPayment, payment_body, verify_payment


def get_order(conn, workspace_id, order_id):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT * FROM billing_orders WHERE id=%s AND workspace_id=%s FOR UPDATE',
                    (order_id, workspace_id))
        order = cur.fetchone()
    if order is None:
        raise ApiError(404, 'not_found')
    return order


def reserve(conn, ws, payload, config):
    workspace_exclusive(conn, ws.id)
    existing = conn.execute('SELECT id,sku,terms_sha256,amount_minor FROM billing_orders WHERE id=%s AND workspace_id=%s',
                            (payload.request_id, ws.id)).fetchone()
    if existing:
        if existing[1:3] != (payload.sku, payload.terms_sha256) or (payload.expected_amount_minor is not None and existing[3] != payload.expected_amount_minor):
            raise ApiError(409, 'billing_idempotency_conflict')
        return get_order(conn, ws.id, payload.request_id)
    if payload.terms_sha256 != config.terms_sha256:
        raise ApiError(409, 'billing_terms_changed')
    scope = conn.execute('SELECT * FROM billing_scope(%s)', (ws.id,)).fetchone()
    if scope[0] != ws.id or (scope[1] > 1 and payload.sku != 'agency'):
        raise ApiError(409, 'billing_bundle_managed', message='Подписка клиентского пакета оплачивается в основном пространстве по тарифу «Агентство».')
    state = load_state(conn, ws.id, None, datetime.now(timezone.utc))
    if state.workspace_status != 'active' or state.paid:
        raise ApiError(409, 'billing_existing_subscription', message='Новая покупка доступна после окончания текущего оплаченного доступа.')
    if conn.execute("SELECT 1 FROM billing_orders WHERE workspace_id=%s AND status IN ('creating','pending','review_required')",
                    (ws.id,)).fetchone():
        raise ApiError(409, 'billing_order_pending', message='Сначала проверьте состояние предыдущего заказа.')
    plan = next(p for p in PLANS if p['id'] == payload.sku)
    if payload.expected_amount_minor is not None:
        remaining = conn.execute('SELECT founder_offer(%s,%s,%s,%s)',
            (ws.actor.user_id, ws.id, config.test, payload.sku == 'control' and payload.expected_amount_minor == 199000)).fetchone()[0]
        amount = 199000 if payload.sku == 'control' and remaining else plan['amount_minor']
        if amount != payload.expected_amount_minor:
            raise ApiError(409, 'billing_offer_changed', message='Цена предложения изменилась. Обновите тарифы перед оплатой.')
        plan = dict(plan, amount_minor=amount)
    email = conn.execute('SELECT email FROM users WHERE id=%s AND status=\'active\'', (ws.actor.user_id,)).fetchone()
    if (not email or not email[0] or '@' not in email[0] or '\r' in email[0] or '\n' in email[0]
            or parseaddr(email[0])[1] != email[0]):
        raise ApiError(409, 'billing_email_required')
    body = payment_body(config, payload.request_id, ws.id, plan, email[0])
    conn.execute('''INSERT INTO billing_orders(id,workspace_id,actor_id,sku,plan,amount_minor,terms_sha256,
                    provider_body,test,shop_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                 (payload.request_id, ws.id, ws.actor.user_id, plan['id'], plan['plan'], plan['amount_minor'],
                  config.terms_sha256, Jsonb(body), config.test, config.shop_id))
    return get_order(conn, ws.id, payload.request_id)


def can_create(order, now):
    return order['status'] == 'creating' and now < order['created_at'] + timedelta(hours=24)


def apply_payment(conn, config, order, payment):
    verify_payment(config, payment, order)
    conn.execute('UPDATE billing_orders SET provider_status=%s,verified_at=now() WHERE id=%s',
                 (payment['status'], order['id']))
    try:
        refund_amount = payment.get('refunded_amount', {'value': '0', 'currency': 'RUB'})
        refunded = Decimal(refund_amount['value'])
        if (not refunded.is_finite() or refunded < 0 or refund_amount['currency'] != 'RUB'
                or refunded > Decimal(order['amount_minor']) / 100
                or refunded * 100 != (refunded * 100).to_integral_value()):
            raise InvalidPayment()
    except (KeyError, TypeError, InvalidOperation):
        raise InvalidPayment() from None
    if refunded > 0:
        # Refunds are initiated in the merchant cabinet; any refunded access needs operator review.
        if order['subscription_id']:
            conn.execute("UPDATE subscriptions SET status='expired',auto_renew=false WHERE id=%s", (order['subscription_id'],))
        conn.execute("UPDATE billing_orders SET status='review_required',refunded_minor=%s,provider_body='{}' WHERE id=%s",
                     (int(refunded * 100), order['id']))
        conn.execute("UPDATE payments SET status='refunded',updated_at=now() WHERE provider_payment_id=%s", (payment['id'],))
        return
    if order['status'] in ('succeeded', 'review_required'):
        return
    if payment['status'] == 'succeeded':
        state = load_state(conn, order['workspace_id'], None, datetime.now(timezone.utc))
        if state.workspace_status != 'active' or state.paid:
            conn.execute("UPDATE billing_orders SET status='review_required',provider_body='{}' WHERE id=%s", (order['id'],))
            return
        conn.execute("UPDATE subscriptions SET status='expired',auto_renew=false WHERE workspace_id=%s AND status<>'expired'",
                     (order['workspace_id'],))
        sub_id = conn.execute('''INSERT INTO subscriptions(workspace_id,plan,status,price,current_period_start,
            current_period_end,auto_renew) VALUES(%s,%s,'active',%s,now(),now()+interval '30 days',false) RETURNING id''',
                              (order['workspace_id'], order['plan'], Decimal(order['amount_minor']) / 100)).fetchone()[0]
        conn.execute('''INSERT INTO payments(subscription_id,provider,provider_payment_id,amount,status)
                        VALUES(%s,'yookassa',%s,%s,'succeeded')''',
                     (sub_id, payment['id'], Decimal(order['amount_minor']) / 100))
        conn.execute("INSERT INTO subscription_events(subscription_id,type,payload) VALUES(%s,'paid',%s)",
                     (sub_id, Jsonb({'order_id': str(order['id']), 'provider_payment_id': payment['id']})))
        conn.execute("UPDATE billing_orders SET status='succeeded',subscription_id=%s,fulfilled_at=now(),provider_body='{}' WHERE id=%s",
                     (sub_id, order['id']))
    elif payment['status'] == 'canceled':
        conn.execute("UPDATE billing_orders SET status='canceled',provider_body='{}' WHERE id=%s", (order['id'],))
    else:
        conn.execute("UPDATE billing_orders SET status='pending' WHERE id=%s", (order['id'],))


def public_order(order):
    return {'id': str(order['id']), 'sku': order['sku'], 'status': order['status'],
            'amount_minor': order['amount_minor'], 'currency': 'RUB', 'test': order['test'],
            'period_days': 30, 'grace_days': 3, 'auto_renew': False}
