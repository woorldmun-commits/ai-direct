"""Вход через Яндекс ID — приложение входа (права login:info, login:email), не API-приложение Директа/Метрики.

Токен приложения входа нужен один раз — прочитать id, login и email — и нигде не сохраняется: хранить токены,
которые продукту больше не нужны, незачем (152-ФЗ, минимизация). Локальный пользователь привязан к устойчивому
Yandex id (yandex_identities.yandex_uid), а не к login. В cookie уходит случайный токен сессии, в БД — его sha256."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Mapping

import httpx
import psycopg

from app.auth.yandex_oauth import TIMEOUT, OAuthApp, OAuthError, ReauthorizationRequired, exchange_code
from app.legal.documents import DEFAULT_LOCALE, is_published, normalize_locale, record_acceptance

INFO_URL = "https://login.yandex.ru/info"
SCOPES = ("login:info", "login:email")
SESSION_TTL = timedelta(days=30)
# Документы, которые пользователь принимает на сайте до перехода в Яндекс ID (версия = дата редакции). Версия должна
# быть в реестре текстов (app/legal/documents.py): хэш принятого текста пишется вместе с принятием.
DOCUMENTS = frozenset({"offer", "pd_consent", "marketing"})
# Согласие на обработку ПД — отдельный документ (ч. 1 ст. 9 152-ФЗ в ред. 156-ФЗ) и обязательно вместе с офертой.
# Решение принято с запасом: если юрист сочтёт основание «договор» достаточным, требование можно ослабить.
REQUIRED_FOR_SIGN_UP = frozenset({"offer", "pd_consent"})


class LoginError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code  # state_mismatch · foreign_token · email_missing · user_deactivated · terms_not_accepted


@dataclass(frozen=True)
class YandexUser:
    uid: str
    login: str
    email: str | None


@dataclass(frozen=True)
class SignedIn:
    user_id: int
    session_token: str = field(repr=False)  # только в cookie
    expires_at: datetime
    created: bool  # первый вход: пользователь только что создан


def login_app() -> OAuthApp:
    return OAuthApp.from_env("YANDEX_LOGIN", SCOPES)


def fetch_user(http: httpx.Client, app: OAuthApp, access_token: str) -> YandexUser:
    try:
        r = http.get(INFO_URL, params={"format": "json"}, headers={"Authorization": f"OAuth {access_token}"},
                     timeout=TIMEOUT)
    except httpx.TransportError:
        raise OAuthError("yandex_unavailable") from None
    if r.status_code == 401:
        raise ReauthorizationRequired("invalid_token")
    if r.status_code != 200:
        raise OAuthError("yandex_unavailable" if r.status_code >= 500 else f"http_{r.status_code}")
    body = r.json()
    if body.get("client_id") != app.client_id:
        raise LoginError("foreign_token")  # токен выдан другому приложению — не наш вход
    return YandexUser(str(body["id"]), body["login"], body.get("default_email"))


def sign_in(conn: psycopg.Connection, http: httpx.Client, app: OAuthApp, *, code: str, state: str,
            expected_state: str, now: datetime, accepted: Mapping[str, str], locale: str = DEFAULT_LOCALE,
            ip: str | None = None, user_agent: str | None = None) -> SignedIn:
    """Callback OAuth: state → обмен кода → профиль → локальный пользователь → сессия.
    accepted — документ → версия, которые пользователь принял на сайте перед входом; для нового пользователя
    обязательны оферта и согласие на обработку ПД. Принятое записывается в legal_acceptances в той же
    транзакции, что и пользователь: с sha256 текста этой версии на языке locale, IP и User-Agent запроса
    (если известны)."""
    if not expected_state or not hmac.compare_digest(state.encode(), expected_state.encode()):
        raise LoginError("state_mismatch")  # до обращения к Яндексу: чужой callback код не обменивает
    locale = normalize_locale(locale)
    if not (accepted.keys() <= DOCUMENTS and all(isinstance(v, str) and is_published(d, v, locale)
                                                 for d, v in accepted.items())):
        raise LoginError("terms_not_accepted")  # неизвестный документ, версия или язык — такого текста не показывали
    user = fetch_user(http, app, exchange_code(http, app, code, now).access_token)
    with conn.transaction():
        user_id, created = _local_user(conn, user, accepted)
        for document, version in sorted(accepted.items()):
            record_acceptance(conn, user_id=user_id, document=document, version=version, accepted_at=now,
                              locale=locale, ip=ip, user_agent=user_agent)
        token = secrets.token_urlsafe(32)
        expires_at = now + SESSION_TTL
        conn.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (%s, %s, %s, %s)",
                     (hashlib.sha256(token.encode()).digest(), user_id, now, expires_at))
    return SignedIn(user_id, token, expires_at, created)


def _local_user(conn: psycopg.Connection, user: YandexUser, accepted: Mapping[str, str]) -> tuple[int, bool]:
    if existing := _existing(conn, user.uid):
        return existing, False
    if not REQUIRED_FOR_SIGN_UP <= accepted.keys():
        raise LoginError("terms_not_accepted")  # без оферты и согласия на ПД — ни договора, ни основания хранить email
    if not user.email:
        raise LoginError("email_missing")  # email нужен для уведомлений о биллинге (users.email NOT NULL)
    try:
        with conn.transaction():  # savepoint: параллельный первый вход того же id (двойной клик на callback)
            user_id = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id", (user.email,)).fetchone()[0]
            conn.execute("INSERT INTO yandex_identities (user_id, yandex_uid, login) VALUES (%s, %s, %s)",
                         (user_id, user.uid, user.login))
    except psycopg.errors.UniqueViolation:
        return _existing(conn, user.uid), False
    return user_id, True


def _existing(conn: psycopg.Connection, uid: str) -> int | None:
    row = conn.execute("""SELECT u.id, u.status FROM yandex_identities i JOIN users u ON u.id = i.user_id
                          WHERE i.yandex_uid = %s""", (uid,)).fetchone()
    if row and row[1] != "active":
        raise LoginError("user_deactivated")
    return row[0] if row else None
