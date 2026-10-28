"""Fixed-host YooKassa adapter. Payment details never pass through our server."""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import httpx


class ProviderUnavailable(Exception):
    pass


class InvalidPayment(ValueError):
    pass


@dataclass(frozen=True)
class BillingConfig:
    shop_id: str
    secret: str = field(repr=False)
    origin: str
    terms_sha256: str
    vat_code: int
    tax_system_code: int
    test: bool = True
    payment_subject: str = 'service'
    payment_mode: str = 'full_payment'

    def __post_init__(self):
        u = urlsplit(self.origin)
        if (not self.shop_id.isdigit() or not self.secret or u.scheme != 'https' or not u.hostname
                or u.username or u.password or u.path or u.query or u.fragment
                or not re.fullmatch('[a-f0-9]{64}', self.terms_sha256)
                or self.vat_code not in range(1, 13) or self.tax_system_code not in range(1, 7)
                or self.payment_subject not in ('service', 'intellectual_activity')
                or self.payment_mode not in ('full_payment', 'full_prepayment')):
            raise ValueError('Incomplete billing configuration')

    @classmethod
    def from_env(cls, env):
        if env.get('INROU_BILLING_ENABLED') != '1':
            return None
        if env.get('INROU_BILLING_LEGAL_APPROVED') != '1':
            raise ValueError('Billing requires approved terms and fiscal settings')
        if env.get('YOOKASSA_TEST_MODE') not in ('0', '1'):
            raise ValueError('Explicit YooKassa test mode is required')
        test = env['YOOKASSA_TEST_MODE'] == '1'
        if not test and env.get('INROU_BILLING_LIVE_APPROVED') != '1':
            raise ValueError('Live billing requires explicit approval')
        return cls(env.get('YOOKASSA_SHOP_ID', ''), env.get('YOOKASSA_SECRET_KEY', ''),
                   env.get('INROU_BILLING_ORIGIN', ''), env.get('INROU_BILLING_TERMS_SHA256', ''),
                   int(env.get('YOOKASSA_VAT_CODE', '0')), int(env.get('YOOKASSA_TAX_SYSTEM_CODE', '0')), test,
                   env.get('YOOKASSA_PAYMENT_SUBJECT', ''), env.get('YOOKASSA_PAYMENT_MODE', ''))


def payment_body(config, order_id, workspace_id, plan, email):
    amount = {'value': format(Decimal(plan['amount_minor']) / 100, '.2f'), 'currency': 'RUB'}
    return {'amount': amount, 'capture': True, 'save_payment_method': False,
            'confirmation': {'type': 'redirect', 'return_url': config.origin + '/workspace/plans?workspace=ws_' + str(workspace_id)},
            'description': 'inrou: ' + plan['name'] + ', 30 дней',
            'metadata': {'order_id': str(order_id), 'workspace_id': str(workspace_id)},
            'receipt': {'customer': {'email': email}, 'tax_system_code': config.tax_system_code,
                        'items': [{'description': 'inrou: ' + plan['name'] + ', 30 дней', 'quantity': '1.00',
                                   'amount': amount, 'vat_code': config.vat_code,
                                   'payment_subject': config.payment_subject, 'payment_mode': config.payment_mode}]}}


def request(config, method, path, *, body=None, key=None):
    if (not re.fullmatch(r'(payments|refunds)(/[A-Za-z0-9-]{1,64})?', path)
            or method not in ('GET', 'POST') or (method == 'POST' and (path != 'payments' or not key))):
        raise ValueError('Invalid provider path')
    try:
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            response = client.request(method, 'https://api.yookassa.ru/v3/' + path,
                                      auth=(config.shop_id, config.secret), json=body,
                                      headers={'Idempotence-Key': str(key)} if key else {})
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError()
            return result
    except (httpx.HTTPError, ValueError):
        # Even HTTP 500 is uncertain: the durable order remains recoverable.
        raise ProviderUnavailable() from None


def verify_payment(config, payment, order):
    try:
        amount = Decimal(payment['amount']['value'])
        if (not amount.is_finite() or amount != Decimal(order['amount_minor']) / 100
                or payment['amount']['currency'] != 'RUB'
                or payment['recipient']['account_id'] != config.shop_id
                or order['shop_id'] != config.shop_id
                or payment['test'] is not config.test
                or payment['metadata']['order_id'] != str(order['id'])
                or payment['metadata']['workspace_id'] != str(order['workspace_id'])
                or payment['id'] != order['provider_payment_id']
                or payment['status'] not in ('pending', 'waiting_for_capture', 'succeeded', 'canceled')
                or (payment['status'] == 'succeeded' and payment.get('paid') is not True)):
            raise InvalidPayment()
    except (KeyError, TypeError, InvalidOperation):
        raise InvalidPayment() from None


def confirmation_url(payment):
    value = payment.get('confirmation', {}).get('confirmation_url')
    if value is None:
        return None
    try:
        u = urlsplit(value)
        if u.scheme != 'https' or u.hostname not in ('yoomoney.ru', 'yookassa.ru') or u.username or u.password or u.port not in (None, 443):
            raise InvalidPayment()
    except (TypeError, ValueError):
        raise InvalidPayment() from None
    return value
