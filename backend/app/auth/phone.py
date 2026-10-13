"""Вход по номеру телефона: выдача и проверка одноразового SMS-кода с лимитами (D2, API_CONTRACT §11).

Юридически вход по SMS на HOLD (LEGAL.md, ст. 10 149-ФЗ): модуль работает только при PHONE_AUTH_ENABLED=1, по
умолчанию выключен. Вход через Яндекс ID (login.py) не затрагивается. Реального SMS-провайдера нет — интерфейс
SmsSender (провайдер только российский); капча — CaptchaVerifier (Yandex SmartCaptcha позже).

Что где:
- номер → E.164, только российские мобильные (phone_number.py) — иначе отказ без отправки и без записи кода;
- код — 6 цифр из secrets; в БД только HMAC-SHA256(ключ из env, номер + код); номер, IP, device id — только HMAC;
- лимиты, гашение предыдущего кода, журнал — атомарно в PostgreSQL (phone_code_request под блокировкой);
- проверка: живой код под блокировкой строки, сравнение hmac.compare_digest, до 5 попыток, одноразовый.
Ответ на принятый запрос кода всегда один и тот же (CodeRequested) — зарегистрирован ли номер, не раскрывается и
здесь даже не проверяется; превышение лимита — RateLimited(retry_after), подозрительная активность — CaptchaRequired.
"""

import hashlib
import hmac
import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Mapping, Protocol

import psycopg
from psycopg.pq import TransactionStatus

from app.auth.phone_number import InvalidPhone, normalize_phone, phone_prefix

log = logging.getLogger(__name__)

CODE_DIGITS = 6
CODE_TTL = timedelta(minutes=5)
MAX_ATTEMPTS = 5  # зашито и в схеме (CHECK attempts ≤ 5, phone_code_for_check)
COOLDOWN = timedelta(seconds=60)
PER_PHONE_HOUR = 5
PER_PHONE_DAY = 10
PER_IP_HOUR = 20
CAPTCHA_AFTER_IP = 3  # с IP за час уже выдано столько кодов → следующий только с капчей
CAPTCHA_AFTER_DEVICE = 3
DEFAULT_DAILY_CAP = 500  # глобальный потолок отправок за скользящие сутки (бюджет SMS)
RETENTION = timedelta(days=30)
MIN_KEY_LENGTH = 32
SMS_TEXT = "Код входа AdPilot: {code}. Никому его не сообщайте."
_TRUE = {"1", "true", "yes", "on"}


class PhoneAuthDisabled(Exception):
    """Вход по телефону выключен (PHONE_AUTH_ENABLED) — юридический HOLD."""


class SmsSendError(Exception):
    """Провайдер не принял SMS."""


class SmsSender(Protocol):
    def send(self, phone_e164: str, text: str) -> None:
        """Отправить SMS; ошибка — SmsSendError. Номер и текст никуда не логируются."""


class CaptchaVerifier(Protocol):
    def verify(self, token: str, ip: str) -> bool:
        """Токен капчи действителен для этого IP."""


@dataclass(frozen=True)
class PhoneAuthConfig:
    enabled: bool
    hmac_key: bytes = field(repr=False)
    daily_cap: int = DEFAULT_DAILY_CAP

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "PhoneAuthConfig":
        env = os.environ if env is None else env
        if env.get("PHONE_AUTH_ENABLED", "").strip().lower() not in _TRUE:
            return cls(enabled=False, hmac_key=b"")
        key = env.get("PHONE_AUTH_HMAC_KEY", "").encode()
        if len(key) < MIN_KEY_LENGTH:
            raise RuntimeError(f"PHONE_AUTH_HMAC_KEY: нужно не меньше {MIN_KEY_LENGTH} байт")
        cap = int(env.get("PHONE_AUTH_DAILY_SEND_CAP", DEFAULT_DAILY_CAP))
        if cap < 1:
            raise RuntimeError("PHONE_AUTH_DAILY_SEND_CAP: нужно положительное число")
        return cls(enabled=True, hmac_key=key, daily_cap=cap)

    def digest(self, purpose: str, value: str) -> bytes:
        """HMAC-SHA256 с разделением по назначению: хэш номера не совпадает с хэшем IP или кода."""
        return hmac.new(self.hmac_key, f"{purpose}\x00{value}".encode(), hashlib.sha256).digest()


@dataclass(frozen=True)
class CodeRequested:
    """Одинаковый ответ на любой принятый запрос: код отправлен или нет — снаружи не видно (API: 202)."""


@dataclass(frozen=True)
class RateLimited:
    retry_after: int  # секунд (API: 429 rate_limited + Retry-After)


@dataclass(frozen=True)
class CaptchaRequired:
    """Нужна капча: подозрительная активность с IP или устройства."""


RequestResult = CodeRequested | RateLimited | CaptchaRequired


def _enabled(config: PhoneAuthConfig) -> None:
    if not config.enabled:
        raise PhoneAuthDisabled("phone_auth_disabled")


def _idle(conn: psycopg.Connection) -> None:
    # Выдача коммитится до отправки SMS: внутри чужой транзакции код ушёл бы раньше, чем записан.
    if conn.info.transaction_status != TransactionStatus.IDLE:
        raise RuntimeError("phone auth: нужна отдельная транзакция (соединение вне транзакции)")


def _code_hash(config: PhoneAuthConfig, phone: str, code: str) -> bytes:
    return config.digest("code", f"{phone}:{code}")


def request_code(conn: psycopg.Connection, *, config: PhoneAuthConfig, sender: SmsSender,
                 captcha: CaptchaVerifier, phone: str, ip: str, now: datetime, device_id: str | None = None,
                 captcha_token: str | None = None) -> RequestResult:
    """POST /auth/code/request. Невалидный номер — InvalidPhone (отправки нет, в журнале — только хэш IP)."""
    _enabled(config)
    _idle(conn)
    if not ip:
        raise ValueError("ip: нужен для лимита на IP")
    ip_hash = config.digest("ip", ip)
    device_hash = config.digest("device", device_id) if device_id else None
    try:
        e164 = normalize_phone(phone)
    except InvalidPhone:
        conn.execute("SELECT phone_auth_log('number_rejected', NULL, %s, %s, NULL, %s)", (ip_hash, device_hash, now))
        raise
    phone_hash, prefix = config.digest("phone", e164), phone_prefix(e164)
    captcha_ok = bool(captcha_token) and captcha.verify(captcha_token, ip)  # HTTP — до транзакции, не внутри
    code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
    with conn.transaction():
        status, retry_after = conn.execute(
            "SELECT status, retry_after FROM phone_code_request(%s, %s, %s, %s, %s, %s, %s, "
            "%s, %s, %s, %s, %s, %s, %s, %s)",
            (phone_hash, ip_hash, device_hash, prefix, _code_hash(config, e164, code), captcha_ok, now,
             int(CODE_TTL.total_seconds()), int(COOLDOWN.total_seconds()), PER_PHONE_HOUR, PER_PHONE_DAY,
             PER_IP_HOUR, config.daily_cap, CAPTCHA_AFTER_IP, CAPTCHA_AFTER_DEVICE)).fetchone()
    if status == "global_cap_reached":
        log.error("phone auth: daily SMS cap reached, sending is blocked")  # алерт: бюджет SMS; без номера
        return RateLimited(retry_after)
    if status == "rate_limited":
        return RateLimited(retry_after)
    if status == "captcha_required":
        return CaptchaRequired()
    try:
        sender.send(e164, SMS_TEXT.format(code=code))
        event = "sms_sent"
    except SmsSendError:
        log.warning("phone auth: SMS provider rejected a message")  # без номера и кода
        event = "sms_failed"
    conn.execute("SELECT phone_auth_log(%s, %s, %s, %s, %s, %s)", (event, phone_hash, ip_hash, device_hash, prefix,
                                                                    now))
    return CodeRequested()


def verify_code(conn: psycopg.Connection, *, config: PhoneAuthConfig, phone: str, code: str, ip: str,
                now: datetime, consume: bool = True) -> str | None:
    """Проверка кода. Верный — номер в E.164 (код погашен, если consume); иначе None — один ответ на неверный,
    истёкший, использованный, погашенный новым и исчерпавший попытки код (API: 401 invalid_code).
    consume=False — код верный, но вход ещё не завершён (нужно принять оферту): код остаётся живым."""
    _enabled(config)
    _idle(conn)
    try:
        e164 = normalize_phone(phone)
    except InvalidPhone:
        return None
    phone_hash, prefix = config.digest("phone", e164), phone_prefix(e164)
    well_formed = isinstance(code, str) and len(code) == CODE_DIGITS and code.isascii() and code.isdigit()
    given = _code_hash(config, e164, code if well_formed else "")
    with conn.transaction():
        row = conn.execute("SELECT code_id, code_hash FROM phone_code_for_check(%s, %s)", (phone_hash, now)).fetchone()
        stored = bytes(row[1]) if row else secrets.token_bytes(32)  # сравнение всегда, время не зависит от кода
        ok = hmac.compare_digest(stored, given) and row is not None and well_formed
        verified = conn.execute("SELECT phone_code_record(%s, %s, %s, %s, %s, %s, %s)",
                                (row[0] if row else None, phone_hash, ok, consume, config.digest("ip", ip or ""),
                                 prefix, now)).fetchone()[0]
    return e164 if verified else None


def hourly_counters(conn: psycopg.Connection, *, now: datetime) -> dict[tuple[str, str | None], int]:
    """Счётчики за последний час (событие, префикс +79XX) → число — для алертов: всплеск отправок или неверных кодов
    по префиксу — признак SMS pumping или перебора. Отказ по глобальному потолку — событие global_cap_reached."""
    rows = conn.execute("SELECT event, phone_prefix, n FROM phone_auth_last_hour(%s)", (now,)).fetchall()
    return {(event, prefix): n for event, prefix, n in rows}


def purge_phone_auth(conn: psycopg.Connection, *, now: datetime) -> int:
    """Ретеншн: журнал и истёкшие коды старше 30 дней. Роль app_deleter. Повторный запуск безопасен (0)."""
    if now.tzinfo is None:
        raise ValueError("now: нужна дата с часовым поясом")
    return conn.execute("SELECT purge_phone_auth(%s)", (now - RETENTION,)).fetchone()[0]
