"""Email identity with durable throttling, explicit mail delivery and one-use links."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import secrets
from typing import Literal
from uuid import uuid4

import psycopg

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from app.api.auth import LoginStart, _approved
from app.api.db import request_connection
from app.api.errors import ApiError
from app.auth.email_password import DUMMY_HASH, mail_token, normalize_email, password_hash, password_matches, token_hash
from app.auth.login import REQUIRED_FOR_SIGN_UP, SESSION_TTL
from app.legal.documents import record_acceptance, text_sha256

router = APIRouter(prefix='/auth')


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(max_length=320)
    password: str = Field(max_length=128)


class Registration(Credentials):
    accepted: dict[str, str] = Field(max_length=3)
    locale: Literal['ru-RU'] = 'ru-RU'


class Address(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(max_length=320)


class Confirmation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')
    password: str = Field(max_length=128)


def _config(request):
    config = request.app.state.settings.email_auth
    if config is None:
        raise ApiError(503, 'auth_unavailable')
    return config


def _address(raw):
    try:
        return normalize_email(raw)
    except ValueError:
        raise ApiError(400, 'invalid_request') from None


@contextmanager
def _connection(request):
    with contextmanager(request_connection)(request) as conn:
        yield conn


def _throttle(request, identity, operation):
    config = _config(request)
    def digest(purpose, value):
        return hmac.new(config.hmac_key.encode(), (purpose+'\x00'+value).encode(), hashlib.sha256).digest()
    # BoundaryMiddleware verifies the frontend's IP signature; arbitrary forwarded headers are ignored.
    peer = request.client.host if request.client else 'unknown'
    with _connection(request) as conn:
        allowed = conn.execute('SELECT email_auth_attempt(%s,%s,%s)',
                               (operation, digest('identity', identity), digest('peer', peer))).fetchone()[0]
    # The reservation commits before any later auth failure can roll it back.
    if not allowed:
        raise ApiError(429, 'rate_limited', message='Слишком много попыток. Попробуйте позже.')


def _kdf(request, callback):
    slots = request.app.state.email_kdf_slots
    if not slots.acquire(blocking=False):
        raise ApiError(503, 'auth_busy')
    try:
        return callback()
    except ValueError:
        raise ApiError(400, 'invalid_request') from None
    finally:
        slots.release()


def _cookie(request, token):
    config = _config(request)
    response = JSONResponse({'status':'signed_in'})
    response.set_cookie(request.app.state.settings.session_cookie, token, httponly=True,
                        secure=config.origin.startswith('https://'), samesite='lax', path='/',
                        max_age=int(SESSION_TTL.total_seconds()))
    return response


def _accepted(request, versions, locale, hashes=None):
    if not REQUIRED_FOR_SIGN_UP <= versions.keys():
        raise ApiError(400, 'invalid_request')
    _approved(request, LoginStart(accepted=versions, locale=locale))
    current = {d:text_sha256(d, v, locale) for d, v in versions.items()}
    if hashes is not None and current != hashes:
        raise ApiError(503, 'legal_unavailable')
    return current


@router.get('/config')
def auth_config(request: Request):
    return {'email_enabled': request.app.state.settings.email_auth is not None}


@router.post('/email/register', status_code=202)
def register(request: Request, body: Registration):
    config = _config(request)
    hashes = _accepted(request, body.accepted, body.locale)
    address = _address(body.email)
    _throttle(request, address, 'send')
    pwd = _kdf(request, lambda: password_hash(body.password))
    job_id = uuid4()
    token = mail_token(config.hmac_key, job_id, 'verify')
    try:
        with _connection(request) as conn:
            created = conn.execute('SELECT email_auth_signup(%s,%s,%s,%s,%s,%s,%s,%s)',
                                  (address, pwd, token_hash(token), Jsonb(body.accepted), Jsonb(hashes), body.locale,
                                   request.client.host if request.client else None,
                                   request.headers.get('user-agent', '')[:256])).fetchone()[0]
            if created:
                conn.execute('SELECT enqueue_email_verify_mail(%s,%s,%s)', (job_id, address, token_hash(token)))
    except psycopg.Error:
        raise ApiError(503, 'mail_unavailable') from None
    return {'status':'check_email'}


@router.post('/email/login')
def login(request: Request, body: Credentials):
    _config(request)
    address = _address(body.email)
    _throttle(request, address, 'login')
    with _connection(request) as conn:
        row = conn.execute('SELECT * FROM email_auth_credential(%s)', (address,)).fetchone()
    pwd = row[1] if row else DUMMY_HASH
    matches = _kdf(request, lambda: password_matches(body.password, pwd))
    if not row or not matches or row[2] != 'active':
        raise ApiError(401, 'unauthenticated', message='Неверный email или пароль.')
    token = secrets.token_urlsafe(32)
    with _connection(request) as conn:
        ok = conn.execute('SELECT email_auth_login(%s,%s,%s)', (address, pwd, token_hash(token))).fetchone()[0]
        if not ok:
            raise ApiError(401, 'unauthenticated')
        old = request.cookies.get(request.app.state.settings.session_cookie)
        if old:
            conn.execute('DELETE FROM sessions WHERE token_hash=%s AND user_id=%s', (token_hash(old), row[0]))
    return _cookie(request, token)


@router.post('/email/verify')
def verify(request: Request, body: Confirmation):
    _config(request)
    _throttle(request, body.token, 'confirm')
    with _connection(request) as conn:
        row = conn.execute('SELECT * FROM email_auth_pending(%s)', (token_hash(body.token),)).fetchone()
    if not _kdf(request, lambda: password_matches(body.password, row[1] if row else DUMMY_HASH)) or not row:
        raise ApiError(400, 'invalid_request')
    address, pwd, versions, hashes, locale, accepted_at, ip, agent = row
    _accepted(request, versions, locale, hashes)
    token = secrets.token_urlsafe(32)
    with _connection(request) as conn:
        uid = conn.execute('SELECT email_auth_finish(%s,%s)', (token_hash(body.token), pwd)).fetchone()[0]
        if uid is None:
            raise ApiError(400, 'invalid_request')
        for document, version in sorted(versions.items()):
            record_acceptance(conn, user_id=uid, document=document, version=version, accepted_at=accepted_at,
                              locale=locale, ip=ip, user_agent=agent)
        org = conn.execute("SELECT create_organization(%s,'Моя организация','business')", (uid,)).fetchone()[0]
        ws = conn.execute("SELECT create_workspace(%s,%s,'Мой кабинет')", (uid, org)).fetchone()[0]
        conn.execute('SELECT start_registration_trial(%s,%s)', (uid, ws))
        conn.execute('INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(%s,%s,%s)',
                     (token_hash(token), uid, datetime.now(timezone.utc)+SESSION_TTL))
    return _cookie(request, token)


@router.post('/email/reset-request', status_code=202)
def reset_request(request: Request, body: Address):
    _config(request)
    address = _address(body.email)
    _throttle(request, address, 'send')
    # Queue every valid address before account lookup; provider failures cannot identify an account.
    try:
        with _connection(request) as conn:
            conn.execute('SELECT enqueue_email_reset_mail(%s,%s)', (uuid4(), address))
    except psycopg.Error:
        raise ApiError(503, 'mail_unavailable') from None
    return {'status':'check_email'}


@router.post('/email/reset')
def reset(request: Request, body: Confirmation):
    _config(request)
    _throttle(request, body.token, 'confirm')
    pwd = _kdf(request, lambda: password_hash(body.password))
    with _connection(request) as conn:
        ok = conn.execute('SELECT email_auth_reset_finish(%s,%s)', (token_hash(body.token), pwd)).fetchone()[0]
        if not ok:
            raise ApiError(400, 'invalid_request')
    return {'status':'password_reset'}
