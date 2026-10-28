"""Real PostgreSQL boundaries; YooKassa itself is never called."""

from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.api.deps import Actor, Workspace
from app.api.errors import ApiError
from app.billing.provider import InvalidPayment
from app.billing import provider
from app.billing.reconcile import reconcile
from app.billing.routes import OrderInput
from app.billing.service import apply_payment, get_order, reserve
from app.tenancy import workspace_scope
from test_api_support import api, cookie, session, user  # noqa: F401
from test_billing import CONFIG, payment
from test_schema import one


@pytest.fixture(scope='module', autouse=True)
def billing_schema(db):
    # Allows the integration owner to run these tests before applying the shared patch.
    with db('app_migrator') as conn:
        if conn.execute("SELECT to_regclass('billing_orders')").fetchone()[0] is None:
            conn.execute((Path(__file__).parents[1]/'app/billing/schema.sql').read_text(encoding='utf-8'))


@pytest.fixture
def purchase(rw):
    owner = user(rw)
    org = one(rw, "SELECT create_organization(%s,'Billing','business')", owner)
    wid = one(rw, "SELECT create_workspace(%s,%s,'Billing')", owner, org)
    ws = Workspace(wid, 'owner', Actor(owner))
    payload = OrderInput(request_id=uuid4(), sku='control', terms_sha256=CONFIG.terms_sha256)
    with rw.transaction():
        saved = reserve(rw, ws, payload, CONFIG)
    return ws, payload, saved


def confirmed(rw, saved):
    pid = str(uuid4())
    rw.execute('UPDATE billing_orders SET provider_payment_id=%s WHERE id=%s', (pid, saved['id']))
    return get_order(rw, saved['workspace_id'], saved['id'])


def test_duplicate_reservation_and_conflict(rw, purchase):
    ws, payload, saved = purchase
    with rw.transaction():
        assert reserve(rw, ws, payload, CONFIG)['id'] == saved['id']
    with pytest.raises(ApiError) as exc, rw.transaction():
        reserve(rw, ws, payload.model_copy(update={'sku': 'business'}), CONFIG)
    assert exc.value.code == 'billing_idempotency_conflict'
    with pytest.raises(ApiError) as exc, rw.transaction():
        reserve(rw, ws, payload.model_copy(update={'request_id': uuid4()}), CONFIG)
    assert exc.value.code == 'billing_order_pending'


def test_success_duplicate_and_transaction_crash(rw, purchase):
    ws, _, saved = purchase
    with rw.transaction():
        o = confirmed(rw, saved)
    with pytest.raises(RuntimeError), rw.transaction():
        apply_payment(rw, CONFIG, o, payment(o))
        raise RuntimeError('synthetic worker crash before commit')
    assert one(rw, 'SELECT count(*) FROM subscriptions WHERE workspace_id=%s', ws.id) == 0
    assert one(rw, 'SELECT status FROM billing_orders WHERE id=%s', o['id']) == 'creating'
    with rw.transaction():
        apply_payment(rw, CONFIG, get_order(rw, ws.id, o['id']), payment(o))
    end = one(rw, 'SELECT current_period_end FROM subscriptions WHERE workspace_id=%s', ws.id)
    with rw.transaction():
        apply_payment(rw, CONFIG, get_order(rw, ws.id, o['id']), payment(o))
    assert one(rw, 'SELECT current_period_end FROM subscriptions WHERE workspace_id=%s', ws.id) == end
    assert one(rw, 'SELECT count(*) FROM payments WHERE provider_payment_id=%s', o['provider_payment_id']) == 1
    assert one(rw, "SELECT count(*) FROM subscription_events WHERE subscription_id=(SELECT subscription_id FROM billing_orders WHERE id=%s) AND type='paid'", o['id']) == 1
    assert one(rw, 'SELECT price FROM subscriptions WHERE workspace_id=%s', ws.id) == 2990
    assert one(rw, 'SELECT auto_renew FROM subscriptions WHERE workspace_id=%s', ws.id) is False


def test_rls_and_immutable_order_evidence(db, rw, purchase):
    ws, _, saved = purchase
    with db('app_rw') as conn:
        assert one(conn, 'SELECT count(*) FROM billing_orders') == 0
        with workspace_scope(conn, ws.id):
            assert one(conn, 'SELECT count(*) FROM billing_orders') == 1
        with workspace_scope(conn, ws.id+100000):
            assert one(conn, 'SELECT count(*) FROM billing_orders WHERE id=%s', saved['id']) == 0
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute('UPDATE billing_orders SET amount_minor=1 WHERE id=%s', (saved['id'],))


def test_deleted_workspace_anonymizes_order_and_receipt(db, rw, purchase):
    ws, _, saved = purchase
    rw.execute("UPDATE workspaces SET status='deletion_pending',deactivated_at=now() WHERE id=%s", (ws.id,))
    with db('app_deleter') as deleter:
        deleter.execute('SELECT delete_workspace_data(%s)', (ws.id,))
    kept = rw.execute('SELECT workspace_id,actor_id,provider_body,status FROM billing_orders WHERE id=%s', (saved['id'],)).fetchone()
    assert kept == (None, None, {}, 'review_required')


def test_forged_amount_grants_nothing(rw, purchase):
    ws, _, saved = purchase
    with rw.transaction():
        o = confirmed(rw, saved)
    p = payment(o)
    p['amount']['value'] = '1.00'
    with pytest.raises(InvalidPayment), rw.transaction():
        apply_payment(rw, CONFIG, o, p)
    assert one(rw, 'SELECT count(*) FROM subscriptions WHERE workspace_id=%s', ws.id) == 0


def test_reconciliation_recovers_confirmed_payment_without_redirect(rw, purchase, monkeypatch):
    ws, _, saved = purchase
    with rw.transaction():
        o = confirmed(rw, saved)
    def current(config, method, path, **kwargs):
        assert method == 'GET'
        pid = path.split('/')[-1]
        wid, oid = rw.execute('SELECT workspace_id,id FROM billing_orders WHERE provider_payment_id=%s', (pid,)).fetchone()
        p = payment(get_order(rw, wid, oid))
        return p
    monkeypatch.setattr(provider, 'request', current)
    result = reconcile(rw, CONFIG)
    assert result['checked'] >= 1 and result['unavailable'] == 0
    assert one(rw, 'SELECT status FROM billing_orders WHERE id=%s', o['id']) == 'succeeded'
    assert one(rw, 'SELECT count(*) FROM payments WHERE provider_payment_id=%s', o['provider_payment_id']) == 1


def test_manager_recovers_order_without_browser_storage(api, rw, purchase):
    ws, _, saved = purchase
    path = f'/api/v1/workspaces/ws_{ws.id}/billing/orders/current'
    assert api.get(path).status_code == 401
    assert api.get(path, headers=cookie(session(rw, user(rw)))).status_code == 404
    response = api.get(path, headers=cookie(session(rw, ws.actor.user_id)))
    assert response.status_code == 200, response.text
    assert response.json()['order'] == {'id': str(saved['id']), 'request_id': str(saved['id']),
        'sku': 'control', 'terms_sha256': CONFIG.terms_sha256}
    assert 'customer' not in response.text and '@' not in response.text


def test_billing_snapshot_retention_is_bounded_audited_and_role_restricted(db, rw, purchase):
    from datetime import datetime, timedelta, timezone
    ws, _, saved = purchase
    now = datetime.now(timezone.utc)
    owner = user(rw)
    org = one(rw, "SELECT create_organization(%s,'Retention','business')", owner)
    old_ws = one(rw, "SELECT create_workspace(%s,%s,'Retention')", owner, org)
    old_id = uuid4()
    rw.execute('''INSERT INTO billing_orders(id,workspace_id,actor_id,sku,plan,amount_minor,terms_sha256,
        provider_body,test,shop_id,created_at) VALUES(%s,%s,%s,'control','start',299000,%s,
        '{"receipt":{"customer":{"email":"synthetic@example.test"}}}',true,%s,%s)''',
        (old_id, old_ws, owner, CONFIG.terms_sha256, CONFIG.shop_id, now-timedelta(hours=25)))
    with db('app_rw') as app:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute('SELECT purge_billing_request_snapshots(%s,1)', (now-timedelta(hours=24),))
    with db('app_deleter') as deleter:
        with pytest.raises(psycopg.errors.RaiseException):
            deleter.execute('SELECT purge_billing_request_snapshots(%s,1)', (now,))
        assert one(deleter, 'SELECT purge_billing_request_snapshots(%s,1)', now-timedelta(hours=24)) == 1
        assert one(deleter, 'SELECT purge_billing_request_snapshots(%s,1)', now-timedelta(hours=24)) == 0
    assert rw.execute('SELECT status,provider_body,id FROM billing_orders WHERE id=%s', (old_id,)).fetchone() == ('review_required', {}, old_id)
    assert one(rw, 'SELECT provider_body FROM billing_orders WHERE id=%s', saved['id'])
    assert one(rw, "SELECT count(*) FROM deletion_requests WHERE deleted_by='purge_billing_request_snapshots'") >= 1
