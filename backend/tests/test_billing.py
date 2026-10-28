"""No external requests: provider verification, retry boundaries, and money transitions."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from threading import BoundedSemaphore
from uuid import uuid4

import httpx
import pytest

from app.api.errors import ApiError
from app.billing import provider, service
from app.billing.catalog import PLANS, account_limit
from app.billing.provider import BillingConfig, InvalidPayment, ProviderUnavailable
from app.billing.routes import Notification, _refresh, webhook

CONFIG = BillingConfig('12345', 'synthetic-test-key', 'https://inrou.example', 'a'*64, 1, 1)
NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)


def order():
    return dict(id=uuid4(), workspace_id=10, actor_id=1, sku='control', plan='start',
                amount_minor=299000, shop_id=CONFIG.shop_id, status='creating', test=True,
                provider_payment_id='synthetic-payment', subscription_id=None, created_at=NOW,
                fulfilled_at=None, refunded_minor=0, provider_body={'opaque': 'saved snapshot'})


def payment(o):
    return dict(id=o['provider_payment_id'], status='succeeded', paid=True,
                amount={'value': '2990.00', 'currency': 'RUB'}, test=True,
                recipient={'account_id': CONFIG.shop_id},
                metadata={'order_id': str(o['id']), 'workspace_id': str(o['workspace_id'])})


def test_catalog_maps_without_repricing_existing_subscriptions():
    assert [(p['id'], p['plan'], p['amount_minor'], p['accounts']) for p in PLANS] == [
        ('control', 'start', 299000, 1), ('business', 'business', 499000, 5),
        ('agency', 'business_plus', 999000, 15)]
    assert account_limit(SimpleNamespace(paid=True, subscription_plan='business_plus')) == 15
    assert account_limit(SimpleNamespace(paid=False, subscription_plan='business_plus')) == 1


def test_config_disabled_and_explicit_approvals():
    assert BillingConfig.from_env({}) is None
    env = {'INROU_BILLING_ENABLED': '1'}
    with pytest.raises(ValueError):
        BillingConfig.from_env(env)
    env.update(INROU_BILLING_LEGAL_APPROVED='1', YOOKASSA_TEST_MODE='0')
    with pytest.raises(ValueError, match='Live billing'):
        BillingConfig.from_env(env)
    assert 'synthetic-test-key' not in repr(CONFIG)
    with pytest.raises(ValueError):
        replace(CONFIG, origin='https://user:password@attacker.example')


def test_request_body_is_exact_minor_units_without_card_or_renewal():
    body = provider.payment_body(CONFIG, uuid4(), 10, PLANS[0], 'owner@example.test')
    assert body['amount'] == {'value': '2990.00', 'currency': 'RUB'}
    assert body['capture'] is True and body['save_payment_method'] is False
    assert body['receipt']['items'][0]['amount'] == body['amount']
    assert body['confirmation']['return_url'] == 'https://inrou.example/workspace/plans?workspace=ws_10'
    assert not {'card', 'payment_method_data', 'payment_method_id'} & body.keys()


@pytest.mark.parametrize('field,value', [
    ('amount', {'value': '2990.01', 'currency': 'RUB'}),
    ('amount', {'value': '2990.00', 'currency': 'USD'}),
    ('amount', {'value': 'NaN', 'currency': 'RUB'}),
    ('recipient', {'account_id': 'another-shop'}), ('test', False),
    ('paid', False), ('id', 'other-payment'), ('status', 'invented'),
    ('metadata', {'order_id': 'other-order', 'workspace_id': '10'}),
    ('metadata', {'order_id': 'ignored', 'workspace_id': '999'}),
])
def test_payment_verification_fails_closed(field, value):
    o = order()
    p = payment(o)
    p[field] = value
    with pytest.raises(InvalidPayment):
        provider.verify_payment(CONFIG, p, o)


def test_verified_current_object_and_shop_snapshot():
    o = order()
    provider.verify_payment(CONFIG, payment(o), o)
    with pytest.raises(InvalidPayment):
        provider.verify_payment(replace(CONFIG, shop_id='99999'), payment(o), o)
    assert service.can_create(o, NOW+timedelta(hours=24)-timedelta(microseconds=1))
    assert not service.can_create(o, NOW+timedelta(hours=24))


@pytest.mark.parametrize('url', ['http://yoomoney.ru/a', 'https://yoomoney.ru.evil.example/a',
    'https://user:password@yoomoney.ru/a', 'https://yoomoney.ru:444/a'])
def test_confirmation_redirect_allowlist(url):
    with pytest.raises(InvalidPayment):
        provider.confirmation_url({'confirmation': {'confirmation_url': url}})


def test_provider_transport_never_redirects_credentials_and_uses_same_key(monkeypatch):
    calls = []
    real_client = httpx.Client
    def handle(req):
        calls.append(req)
        return httpx.Response(500, json={'description': 'uncertain'})
    def client(**kwargs):
        assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False
        return real_client(transport=httpx.MockTransport(handle), **kwargs)
    monkeypatch.setattr(provider.httpx, 'Client', client)
    key = uuid4()
    for _ in range(2):
        with pytest.raises(ProviderUnavailable):
            provider.request(CONFIG, 'POST', 'payments', body={'amount': 'snapshot'}, key=key)
    assert all(str(r.url) == 'https://api.yookassa.ru/v3/payments' for r in calls)
    assert [r.headers['Idempotence-Key'] for r in calls] == [str(key)]*2
    assert calls[0].content == calls[1].content
    with pytest.raises(ValueError):
        provider.request(CONFIG, 'GET', 'payments/../../evil')


class RecordingConnection:
    def __init__(self):
        self.commands = []

    def execute(self, sql, params=()):
        self.commands.append((sql, params))
        return SimpleNamespace(fetchone=lambda: (42,))


def test_same_success_after_fulfillment_never_extends_again():
    conn = RecordingConnection()
    o = order()
    o['status'], o['subscription_id'], o['fulfilled_at'] = 'succeeded', 42, NOW
    service.apply_payment(conn, CONFIG, o, payment(o))
    assert len(conn.commands) == 1 and 'provider_status=' in conn.commands[0][0]


def test_refund_records_actual_amount_and_revokes_linked_subscription():
    conn = RecordingConnection()
    o = order()
    o['status'], o['subscription_id'] = 'succeeded', 42
    p = payment(o)
    p['refunded_amount'] = {'value': '10.00', 'currency': 'RUB'}
    service.apply_payment(conn, CONFIG, o, p)
    assert "status='expired'" in conn.commands[1][0]
    assert conn.commands[2][1] == (1000, o['id'])
    assert "status='refunded'" in conn.commands[3][0]


def test_checkout_creation_always_gets_current_payment_before_fulfillment(monkeypatch):
    conn = RecordingConnection()
    o = order()
    o['provider_payment_id'] = None
    o['created_at'] = datetime.now(timezone.utc)
    ws = SimpleNamespace(id=10, role='owner')
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(billing=CONFIG))))
    calls = []
    monkeypatch.setattr('app.billing.routes.workspace_exclusive', lambda *a: None)
    monkeypatch.setattr('app.billing.routes.get_order', lambda *a: deepcopy(o))
    def request(config, method, path, **kwargs):
        calls.append(method)
        p = payment({**o, 'provider_payment_id': 'synthetic-payment'})
        if method == 'GET':
            raise ProviderUnavailable()
        return p
    monkeypatch.setattr(provider, 'request', request)
    monkeypatch.setattr('app.billing.routes.apply_payment', lambda *a: pytest.fail('GET failure must not fulfill'))
    result = _refresh(req, conn, ws, o['id'], True)
    assert result.status_code == 503
    assert calls == ['POST', 'GET']
    assert any('SET provider_payment_id' in sql for sql, _ in conn.commands)


def test_expired_unknown_creation_never_posts_again(monkeypatch):
    conn = RecordingConnection()
    o = order()
    o['provider_payment_id'] = None
    o['created_at'] = datetime.now(timezone.utc)-timedelta(hours=24)
    ws = SimpleNamespace(id=10, role='owner')
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(billing=CONFIG))))
    monkeypatch.setattr('app.billing.routes.workspace_exclusive', lambda *a: None)
    monkeypatch.setattr('app.billing.routes.get_order', lambda *a: o)
    monkeypatch.setattr(provider, 'request', lambda *a, **k: pytest.fail('unsafe retry'))
    result = _refresh(req, conn, ws, o['id'], True)
    assert result.status_code == 409
    assert 'review_required' in conn.commands[-1][0]


def test_analyzer_cannot_start_payment():
    ws = SimpleNamespace(id=10, role='analyst')
    with pytest.raises(ApiError) as exc:
        _refresh(None, None, ws, uuid4(), True)
    assert exc.value.status == 403


def test_webhook_ignores_body_status_and_amount_and_uses_verified_get(monkeypatch):
    conn = RecordingConnection()
    o = order()
    p = payment(o)
    p['status'], p['paid'] = 'pending', False
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        settings=SimpleNamespace(billing=CONFIG), auth_callbacks=BoundedSemaphore(1))))
    monkeypatch.setattr('app.billing.routes.set_local_workspace', lambda *a: None)
    monkeypatch.setattr('app.billing.routes.workspace_exclusive', lambda *a: None)
    monkeypatch.setattr('app.billing.routes.get_order', lambda *a: o)
    calls, applied = [], []
    def current(config, method, path, **kwargs):
        assert method == 'GET' and path == 'payments/' + p['id']
        calls.append(path)
        return p
    monkeypatch.setattr(provider, 'request', current)
    monkeypatch.setattr('app.billing.routes.apply_payment', lambda conn, config, order, current: applied.append(current))
    assert webhook(req, Notification(type='notification', event='payment.succeeded',
        object={'id': p['id'], 'status': 'succeeded', 'amount': {'value': '1.00'}}), conn) == {'accepted': True}
    assert len(calls) == 1 and applied[0]['status'] == 'pending'


def test_webhook_provider_failure_never_acknowledges(monkeypatch):
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        settings=SimpleNamespace(billing=CONFIG), auth_callbacks=BoundedSemaphore(1))))
    def unavailable(*args, **kwargs):
        raise ProviderUnavailable()
    monkeypatch.setattr(provider, 'request', unavailable)
    with pytest.raises(ApiError) as exc:
        webhook(req, Notification(type='notification', event='payment.succeeded', object={'id': 'synthetic-payment'}), RecordingConnection())
    assert exc.value.status == 503
