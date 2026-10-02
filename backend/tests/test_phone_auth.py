"""Вход по номеру телефона (D2): нормализация, лимиты в PostgreSQL без гонок, капча, код (TTL, попытки,
одноразовость, гашение), одинаковый ответ, флаг, отсутствие номера/кода/IP в открытом виде, журнал и ретеншн."""

import itertools
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from app.auth.phone import (CaptchaRequired, CodeRequested, PhoneAuthConfig, PhoneAuthDisabled, RateLimited,
                            SmsSendError, hourly_counters, purge_phone_auth, request_code, verify_code)
from app.auth.phone_number import InvalidPhone, normalize_phone

KEY = b"k" * 32
CONFIG = PhoneAuthConfig(enabled=True, hmac_key=KEY, daily_cap=1000)
_bases = itertools.count()
_numbers = itertools.count(1000000)


class FakeSms:
    def __init__(self, fail: bool = False):
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    def send(self, phone_e164: str, text: str) -> None:
        if self.fail:
            raise SmsSendError("provider down")
        self.sent.append((phone_e164, text))

    def code(self) -> str:
        return re.search(r"\d{6}", self.sent[-1][1]).group()


class FakeCaptcha:
    def verify(self, token: str, ip: str) -> bool:
        return token == "ok"


@pytest.fixture
def base():
    """Своё «время» каждого теста (шаг 3 дня): суточные окна и глобальный потолок тестов не пересекаются."""
    return datetime(2031, 1, 1, tzinfo=timezone.utc) + timedelta(days=3 * next(_bases))


@pytest.fixture
def app(db):
    with db("app_rw") as conn:
        yield conn


@pytest.fixture
def owner(db):
    """Владелец таблиц — только для проверки содержимого (у рабочих ролей прав на таблицы нет)."""
    with db("app_migrator") as conn:
        yield conn


@pytest.fixture
def sms():
    return FakeSms()


def phone() -> str:
    """Новый российский мобильный номер для теста."""
    return f"+7912{next(_numbers):07d}"


def ip() -> str:
    n = next(_numbers)
    return f"10.{n // 65536 % 256}.{n // 256 % 256}.{n % 256}"


def ask(app, sms, number, at, *, address=None, config=CONFIG, **kw):
    kw.setdefault("captcha_token", "ok")
    return request_code(app, config=config, sender=sms, captcha=FakeCaptcha(), phone=number, ip=address or ip(),
                        now=at, **kw)


def check(app, number, code, at, **kw):
    return verify_code(app, config=CONFIG, phone=number, code=code, ip="10.0.0.1", now=at, **kw)


def events(owner, event, at):
    return owner.execute("SELECT count(*) FROM phone_auth_events WHERE event = %s AND occurred_at = %s",
                         (event, at)).fetchone()[0]


# --- нормализация -----------------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["+7 912 345-67-89", "8 (912) 345 67 89", "79123456789", "+79123456789",
                                 "8-912-345-67-89", " +7(912)3456789 ", "8.912.345.67.89"])
def test_russian_mobile_is_normalized_to_e164(raw):
    assert normalize_phone(raw) == "+79123456789"


@pytest.mark.parametrize("raw", [
    "", None, 79123456789, "9123456789", "+7912345678", "+791234567890", "+7 912 abc 67 89",
    "+7 495 123-45-67",  # городской
    "8 800 555 35 35",   # 8-800 — не мобильный
    "+7 701 123 45 67",  # Казахстан (тот же код страны)
    "+7 940 123 45 67",  # Абхазия
    "+380 50 123 45 67", "+1 202 555 0100", "0079123456789", "+8 912 345 67 89",
    "+7٩١٢٣٤٥٦٧٨٩",      # не-ASCII цифры
    "+7 912 345 67 89" + " " * 40,  # слишком длинная строка
])
def test_everything_else_is_rejected(raw):
    with pytest.raises(InvalidPhone):
        normalize_phone(raw)


def test_invalid_number_is_not_sent_and_logged_without_number(app, owner, sms, base):
    with pytest.raises(InvalidPhone):
        ask(app, sms, "+380501234567", base)
    assert sms.sent == []
    row = owner.execute("SELECT phone_hash, ip_hash, phone_prefix FROM phone_auth_events "
                        "WHERE event = 'number_rejected' AND occurred_at = %s", (base,)).fetchone()
    assert row[0] is None and row[1] is not None and row[2] is None


# --- флаг -------------------------------------------------------------------------------------------

def test_flag_is_off_by_default_and_refuses(app, owner, sms, base):
    config = PhoneAuthConfig.from_env({})
    assert not config.enabled
    with pytest.raises(PhoneAuthDisabled):
        ask(app, sms, phone(), base, config=config)
    with pytest.raises(PhoneAuthDisabled):
        verify_code(app, config=config, phone=phone(), code="123456", ip="1.1.1.1", now=base)
    assert sms.sent == []
    assert owner.execute("SELECT count(*) FROM phone_auth_events WHERE occurred_at = %s", (base,)).fetchone()[0] == 0


def test_enabled_flag_requires_key_and_reads_cap():
    with pytest.raises(RuntimeError):
        PhoneAuthConfig.from_env({"PHONE_AUTH_ENABLED": "1", "PHONE_AUTH_HMAC_KEY": "short"})
    config = PhoneAuthConfig.from_env({"PHONE_AUTH_ENABLED": "true", "PHONE_AUTH_HMAC_KEY": "x" * 32,
                                       "PHONE_AUTH_DAILY_SEND_CAP": "7"})
    assert config.enabled and config.daily_cap == 7
    assert "x" * 32 not in repr(config)
    assert not PhoneAuthConfig.from_env({"PHONE_AUTH_ENABLED": "0", "PHONE_AUTH_HMAC_KEY": "x" * 32}).enabled


# --- код --------------------------------------------------------------------------------------------

def test_code_is_sent_verified_once(app, owner, sms, base):
    number = phone()
    assert ask(app, sms, "8 " + number[2:], base) == CodeRequested()
    assert sms.sent[0][0] == number and re.fullmatch(r"\d{6}", sms.code())
    assert check(app, number, sms.code(), base + timedelta(seconds=10)) == number
    assert check(app, number, sms.code(), base + timedelta(seconds=11)) is None  # одноразовый
    assert events(owner, "code_issued", base) == events(owner, "sms_sent", base) == 1
    assert events(owner, "code_verified", base + timedelta(seconds=10)) == 1


def test_response_is_the_same_whatever_happens_to_the_sms(app, sms, base):
    assert ask(app, sms, phone(), base) == ask(app, FakeSms(fail=True), phone(), base) == CodeRequested()


@pytest.mark.parametrize("after, ok", [(timedelta(minutes=4, seconds=59), True), (timedelta(minutes=5), False)])
def test_code_lives_five_minutes(app, sms, base, after, ok):
    number = phone()
    ask(app, sms, number, base)
    assert (check(app, number, sms.code(), base + after) == number) is ok


@pytest.mark.parametrize("wrong, ok", [(4, True), (5, False)])
def test_five_wrong_attempts_kill_the_code(app, owner, sms, base, wrong, ok):
    number = phone()
    ask(app, sms, number, base)
    bad = f"{(int(sms.code()) + 1) % 1000000:06d}"
    for i in range(wrong):
        assert check(app, number, bad if i % 2 else "12x", base + timedelta(seconds=i + 1)) is None
    assert (check(app, number, sms.code(), base + timedelta(seconds=30)) == number) is ok
    assert owner.execute("SELECT count(*) FROM phone_auth_events WHERE event = 'code_invalid' "
                         "AND occurred_at BETWEEN %s AND %s", (base, base + timedelta(seconds=30))).fetchone()[0] \
        == wrong + (not ok)


def test_new_code_supersedes_previous(app, sms, base):
    number = phone()
    ask(app, sms, number, base)
    first = sms.code()
    ask(app, sms, number, base + timedelta(seconds=61))
    second = sms.code()
    if first != second:
        assert check(app, number, first, base + timedelta(seconds=62)) is None
    assert check(app, number, second, base + timedelta(seconds=63)) == number


def test_unconsumed_check_keeps_code_alive(app, sms, base):
    """422 acceptance_required: код верный, но вход не завершён — код не гасится до истечения."""
    number = phone()
    ask(app, sms, number, base)
    assert check(app, number, sms.code(), base + timedelta(seconds=5), consume=False) == number
    assert check(app, number, sms.code(), base + timedelta(seconds=6)) == number
    assert check(app, number, sms.code(), base + timedelta(seconds=7)) is None


# --- лимиты -----------------------------------------------------------------------------------------

def test_cooldown_sixty_seconds(app, owner, sms, base):
    number = phone()
    ask(app, sms, number, base)
    assert ask(app, sms, number, base + timedelta(seconds=30)) == RateLimited(30)
    assert ask(app, sms, number, base + timedelta(seconds=60)) == CodeRequested()
    assert len(sms.sent) == 2
    assert owner.execute("SELECT reason FROM phone_auth_events WHERE event = 'rate_limited' AND occurred_at = %s",
                         (base + timedelta(seconds=30),)).fetchone()[0] == "cooldown"


def test_five_codes_per_hour_and_ten_per_day(app, owner, sms, base):
    number = phone()
    for i in range(5):
        assert ask(app, sms, number, base + timedelta(seconds=61 * i)) == CodeRequested()
    sixth = base + timedelta(seconds=305)
    assert ask(app, sms, number, sixth) == RateLimited(3600 - 305)
    hour2 = base + timedelta(hours=1, seconds=1)
    for i in range(5):
        assert ask(app, sms, number, hour2 + timedelta(seconds=61 * i)) == CodeRequested()
    later = base + timedelta(hours=3)
    assert ask(app, sms, number, later) == RateLimited(86400 - 3 * 3600)
    assert len(sms.sent) == 10
    assert owner.execute("SELECT reason FROM phone_auth_events WHERE event = 'rate_limited' AND occurred_at = %s",
                         (later,)).fetchone()[0] == "phone_day"


def test_twenty_codes_per_hour_per_ip(app, sms, base):
    address = ip()
    for i in range(20):
        assert ask(app, sms, phone(), base + timedelta(seconds=i), address=address) == CodeRequested()
    assert ask(app, sms, phone(), base + timedelta(seconds=20), address=address) == RateLimited(3600 - 20)
    assert ask(app, sms, phone(), base + timedelta(seconds=20)) == CodeRequested()  # другой IP


def test_global_daily_cap_blocks_and_alerts(app, owner, sms, base, caplog):
    config = PhoneAuthConfig(enabled=True, hmac_key=KEY, daily_cap=3)
    for i in range(3):
        assert ask(app, sms, phone(), base + timedelta(minutes=i), config=config) == CodeRequested()
    blocked = base + timedelta(minutes=10)
    assert ask(app, sms, phone(), blocked, config=config) == RateLimited(86400 - 600)
    assert len(sms.sent) == 3
    assert events(owner, "global_cap_reached", blocked) == 1
    assert "daily SMS cap" in caplog.text


# --- капча ------------------------------------------------------------------------------------------

def test_captcha_after_three_codes_from_ip(app, sms, base):
    address = ip()
    for i in range(3):
        assert ask(app, sms, phone(), base + timedelta(seconds=i), address=address,
                   captcha_token=None) == CodeRequested()
    at = base + timedelta(seconds=5)
    assert ask(app, sms, phone(), at, address=address, captcha_token=None) == CaptchaRequired()
    assert ask(app, sms, phone(), at, address=address, captcha_token="forged") == CaptchaRequired()
    assert ask(app, sms, phone(), at, address=address, captcha_token="ok") == CodeRequested()
    assert len(sms.sent) == 4


def test_captcha_after_three_codes_from_device(app, sms, base):
    for i in range(3):
        assert ask(app, sms, phone(), base + timedelta(seconds=i), device_id="dev-1",
                   captcha_token=None) == CodeRequested()
    assert ask(app, sms, phone(), base + timedelta(seconds=5), device_id="dev-1",
               captcha_token=None) == CaptchaRequired()


# --- параллельные запросы ---------------------------------------------------------------------------

def _wait_for_lock_waiter(owner):
    for _ in range(100):
        if owner.execute("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted").fetchone()[0]:
            return
        time.sleep(0.05)
    raise AssertionError("второй запрос не ждал блокировку")


@pytest.mark.parametrize("same_phone", [True, False])
def test_concurrent_requests_do_not_exceed_limit(db, app, owner, sms, base, same_phone):
    """Первый запрос не закоммичен; второй ждёт его и видит его выдачу: cooldown номера / глобальный потолок."""
    config = CONFIG if same_phone else PhoneAuthConfig(enabled=True, hmac_key=KEY, daily_cap=1)
    number = phone()
    results = []
    with db("app_rw") as other:
        with app.transaction():
            app.execute("SELECT * FROM phone_code_request(%s, %s, NULL, '+7912', %s, true, %s, "
                        "300, 60, 5, 10, 20, 1000, 3, 3)",
                        (config.digest("phone", number), config.digest("ip", "10.9.9.9"), b"c" * 32, base))
            second = threading.Thread(target=lambda: results.append(
                ask(other, sms, number if same_phone else phone(), base + timedelta(seconds=1), config=config)))
            second.start()
            _wait_for_lock_waiter(owner)
        second.join(10)
    assert results == [RateLimited(59 if same_phone else 86399)]
    assert sms.sent == []


def test_request_refuses_snapshot_isolation(db, base):
    with db("app_rw") as conn, pytest.raises(psycopg.errors.RaiseException, match="READ COMMITTED"):
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            conn.execute("SELECT * FROM phone_code_request(%s, %s, NULL, NULL, %s, true, %s, "
                         "300, 60, 5, 10, 20, 1000, 3, 3)", (b"p" * 32, b"i" * 32, b"c" * 32, base))


# --- хранение, права, журнал ------------------------------------------------------------------------

def test_no_number_code_or_ip_in_plain_text(app, owner, sms, base):
    number, address = phone(), "203.0.113.77"
    ask(app, sms, number, base, address=address, device_id="device-secret")
    code = sms.code()
    check(app, number, "000000" if code != "000000" else "111111", base + timedelta(seconds=1))
    window = (base, base + timedelta(seconds=1))
    dump = " ".join(str(r) for r in owner.execute(
        """SELECT t::text FROM phone_auth_codes t WHERE created_at BETWEEN %s AND %s
           UNION ALL SELECT t::text FROM phone_auth_events t WHERE occurred_at BETWEEN %s AND %s""",
        window + window).fetchall())
    assert "code_invalid" in dump and "sms_sent" in dump
    for secret in (number[1:], number[2:], code, address, "device-secret"):
        assert secret not in dump
    row = owner.execute("SELECT phone_hash, code_hash FROM phone_auth_codes WHERE created_at = %s", (base,)).fetchone()
    assert bytes(row[0]) == CONFIG.digest("phone", number) != CONFIG.digest("ip", number)  # HMAC с ключом


@pytest.mark.parametrize("sql", ["SELECT * FROM phone_auth_codes", "SELECT * FROM phone_auth_events",
                                 "INSERT INTO phone_auth_events (occurred_at, event) VALUES (now(), 'code_issued')",
                                 "DELETE FROM phone_auth_events", "SELECT purge_phone_auth(now())"])
def test_app_role_has_no_direct_access(app, sql):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app.execute(sql)


def test_app_cannot_forge_issuance_events(app):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app.execute("SELECT phone_auth_log('code_issued', %s, %s, NULL, NULL, now())", (b"p" * 32, b"i" * 32))


def test_events_are_append_only(owner, app, sms, base):
    ask(app, sms, phone(), base)
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
        owner.execute("UPDATE phone_auth_events SET event = 'sms_failed' WHERE occurred_at = %s", (base,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
        owner.execute("DELETE FROM phone_auth_events WHERE occurred_at = %s", (base,))


def test_hourly_counters_by_prefix(app, sms, base):
    number = phone()
    ask(app, sms, number, base)
    ask(app, sms, number, base + timedelta(seconds=1))
    check(app, number, "12x", base + timedelta(seconds=2))
    with pytest.raises(InvalidPhone):
        ask(app, sms, "+1 202 555 0100", base + timedelta(seconds=3))
    counters = hourly_counters(app, now=base + timedelta(minutes=1))
    assert counters[("code_issued", "+7912")] == 1 and counters[("sms_sent", "+7912")] == 1
    assert counters[("rate_limited", "+7912")] == 1 and counters[("code_invalid", "+7912")] == 1
    assert counters[("number_rejected", None)] == 1
    assert hourly_counters(app, now=base + timedelta(hours=2)) == {}


def test_purge_after_thirty_days(db, app, owner, sms, base):
    old, fresh = base, base + timedelta(days=1)
    ask(app, sms, phone(), old)
    ask(app, sms, phone(), fresh)
    with db("app_deleter") as deleter:
        assert purge_phone_auth(deleter, now=fresh + timedelta(days=30)) >= 3  # старые: код + 2 события
        assert purge_phone_auth(deleter, now=fresh + timedelta(days=30)) == 0  # повтор безопасен
    assert events(owner, "code_issued", old) == 0 and events(owner, "code_issued", fresh) == 1
    assert owner.execute("SELECT count(*) FROM phone_auth_codes WHERE created_at = %s", (old,)).fetchone()[0] == 0
    assert owner.execute("SELECT count(*) FROM deletion_requests WHERE deleted_by = 'purge_phone_auth'"
                         ).fetchone()[0] >= 1
