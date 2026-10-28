"""Two-step checkout: reserve commits before a provider request can begin."""

import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import Conn, CurrentWorkspace, require_manager
from app.api.errors import ApiError
from app.billing import provider
from app.billing.catalog import PLANS
from app.billing.service import apply_payment, can_create, get_order, public_order, reserve
from app.tenancy import set_local_workspace
from app.worker.locks import workspace_exclusive

router = APIRouter()
WEBHOOK_PATH = '/api/v1/billing/yookassa/webhook'


class OrderInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    sku: Literal['control', 'business', 'agency']
    terms_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


def _config(request):
    config = request.app.state.settings.billing
    if config is None:
        raise ApiError(503, 'billing_unavailable', message='Оплата ещё не подключена.')
    return config


@router.get('/billing/plans')
def plans(request: Request):
    config = request.app.state.settings.billing
    return {'items': PLANS, 'unit': 'workspace', 'currency': 'RUB', 'period_days': 30, 'grace_days': 3,
            'auto_renew': False, 'checkout_enabled': config is not None,
            'test': config.test if config else None, 'terms_sha256': config.terms_sha256 if config else None}


@router.post('/workspaces/{workspace_id}/billing/orders')
def create_order(request: Request, payload: OrderInput, conn: Conn, ws: CurrentWorkspace):
    require_manager(ws)
    return public_order(reserve(conn, ws, payload, _config(request)))


@router.get('/workspaces/{workspace_id}/billing/orders/current')
def current_order(conn: Conn, ws: CurrentWorkspace):
    require_manager(ws)
    row = conn.execute("""SELECT id,sku,terms_sha256 FROM billing_orders WHERE workspace_id=%s
        AND status IN ('creating','pending','review_required') ORDER BY created_at DESC LIMIT 1""", (ws.id,)).fetchone()
    return {'order': {'id': str(row[0]), 'request_id': str(row[0]), 'sku': row[1],
                      'terms_sha256': row[2]} if row else None}


def _refresh(request, conn, ws, order_id, create):
    require_manager(ws)
    config = _config(request)
    workspace_exclusive(conn, ws.id)
    order = get_order(conn, ws.id, order_id)
    if order['test'] is not config.test or order['shop_id'] != config.shop_id:
        raise ApiError(409, 'billing_mode_changed')
    try:
        if order['provider_payment_id']:
            payment = provider.request(config, 'GET', 'payments/' + order['provider_payment_id'])
        elif create and can_create(order, datetime.now(timezone.utc)):
            payment = provider.request(config, 'POST', 'payments', body=order['provider_body'], key=order['id'])
            pid = payment.get('id', '')
            if not isinstance(pid, str) or not re.fullmatch('[A-Za-z0-9-]{1,64}', pid):
                raise provider.InvalidPayment()
            order['provider_payment_id'] = pid
            provider.verify_payment(config, payment, order)
            conn.execute('UPDATE billing_orders SET provider_payment_id=%s WHERE id=%s', (pid, order['id']))
            payment = provider.request(config, 'GET', 'payments/' + pid)
        else:
            if create:
                conn.execute("UPDATE billing_orders SET status='review_required',provider_body='{}' WHERE id=%s", (order['id'],))
                return JSONResponse({'error': {'code': 'billing_reconciliation_required',
                    'message': 'Срок безопасного повтора истёк. Требуется сверка платежа оператором.'}}, status_code=409)
            return public_order(order)
        apply_payment(conn, config, order, payment)
        result = public_order(get_order(conn, ws.id, order_id))
        result['confirmation_url'] = provider.confirmation_url(payment) if result['status'] == 'pending' else None
        return result
    except provider.ProviderUnavailable:
        # Return a response, not an exception: known order/payment progress must commit.
        return JSONResponse({'error': {'code': 'billing_provider_unavailable',
            'message': 'Проверьте этот же заказ повторно. Не создавайте новый платёж.'}}, status_code=503)
    except provider.InvalidPayment:
        conn.execute("UPDATE billing_orders SET status='review_required',provider_body='{}' WHERE id=%s", (order['id'],))
        return JSONResponse({'error': {'code': 'billing_verification_failed',
            'message': 'Платёж требует проверки оператором.'}}, status_code=409)


@router.post('/workspaces/{workspace_id}/billing/orders/{order_id}/checkout')
def checkout(request: Request, order_id: UUID, conn: Conn, ws: CurrentWorkspace):
    return _refresh(request, conn, ws, order_id, True)


@router.post('/workspaces/{workspace_id}/billing/orders/{order_id}/refresh')
def refresh(request: Request, order_id: UUID, conn: Conn, ws: CurrentWorkspace):
    return _refresh(request, conn, ws, order_id, False)


class Notification(BaseModel):
    model_config = ConfigDict(extra='ignore')
    type: Literal['notification']
    event: Literal['payment.succeeded', 'payment.canceled', 'payment.waiting_for_capture', 'refund.succeeded']
    object: dict


@router.post('/billing/yookassa/webhook')
def webhook(request: Request, payload: Notification, conn: Conn):
    config = _config(request)
    pid = payload.object.get('id', '')
    if not isinstance(pid, str) or not re.fullmatch('[A-Za-z0-9-]{1,64}', pid):
        raise ApiError(400, 'invalid_request')
    slots = request.app.state.auth_callbacks
    if not slots.acquire(blocking=False):
        raise ApiError(503, 'billing_busy')
    try:
        if payload.event == 'refund.succeeded':
            refund = provider.request(config, 'GET', 'refunds/' + pid)
            pid = refund.get('payment_id', '')
            if refund.get('status') != 'succeeded':
                raise ApiError(409, 'billing_verification_failed')
        payment = provider.request(config, 'GET', 'payments/' + pid)
        if payload.event == 'refund.succeeded' and payment.get('refunded_amount', {}).get('value', '0.00') == '0.00':
            raise ApiError(503, 'billing_refund_pending')
        workspace_id = int(payment['metadata']['workspace_id'])
        order_id = UUID(payment['metadata']['order_id'])
        if workspace_id <= 0 or workspace_id > 2**63-1:
            raise ValueError()
        set_local_workspace(conn, workspace_id)
        workspace_exclusive(conn, workspace_id)
        # Deleted workspaces leave an anonymized order; no entitlement can be recreated.
        if not conn.execute('SELECT 1 FROM billing_orders WHERE workspace_id=%s AND id=%s',
                            (workspace_id, order_id)).fetchone():
            return {'accepted': True}
        order = get_order(conn, workspace_id, order_id)
        if order['provider_payment_id'] is None:
            order['provider_payment_id'] = payment['id']
            provider.verify_payment(config, payment, order)
            conn.execute('UPDATE billing_orders SET provider_payment_id=%s WHERE id=%s', (payment['id'], order_id))
        apply_payment(conn, config, order, payment)
        # Conn commits before HTTP 200; any failure remains eligible for provider redelivery.
        return {'accepted': True}
    except provider.ProviderUnavailable:
        raise ApiError(503, 'billing_provider_unavailable') from None
    except (provider.InvalidPayment, KeyError, TypeError, ValueError):
        raise ApiError(409, 'billing_verification_failed') from None
    finally:
        slots.release()
