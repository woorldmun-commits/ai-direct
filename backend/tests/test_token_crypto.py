"""Шифрование OAuth-токенов подключений: AES-GCM с AAD подключения, версии ключей и ротация без остановки,
обновление пары под блокировкой. Права ролей на шифротекст — tests/test_tokens.py."""

import base64
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import httpx
import pytest

from app.auth.tokens import (ConnectionRef, EnvKeys, TokenDecryptError, decrypt, encrypt, fresh_access_token, load,
                             store)
from app.auth.yandex_oauth import OAuthApp, ReauthorizationRequired, Tokens
from test_schema import chain, connected, one  # noqa: F401 — фикстура
from test_tokens import token_role  # noqa: F401 — фикстура

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
API_APP = OAuthApp("api-client", "api-secret", "https://app.test/connect/callback", ("direct:api",))
ACCESS, REFRESH = "y0_ACCESS-TOKEN-secret", "1:REFRESH-TOKEN-secret"


def keys(current=1, versions=(1,)) -> EnvKeys:
    env = {f"TOKEN_ENCRYPTION_KEY_{v}": base64.b64encode(bytes([v]) * 32).decode() for v in versions}
    return EnvKeys({**env, "TOKEN_ENCRYPTION_KEY_VERSION": str(current)})


REF = ConnectionRef("direct", 7, 42)


# --- Конверт ---------------------------------------------------------------------------------------

def test_roundtrip():
    t = decrypt(keys(), REF, encrypt(keys(), REF, ACCESS, REFRESH))
    assert (t.access_token, t.refresh_token, t.key_version) == (ACCESS, REFRESH, 1)


@pytest.mark.parametrize("other", [ConnectionRef("direct", 7, 43), ConnectionRef("metrika", 7, 42),
                                   ConnectionRef("direct", 8, 42)])
def test_ciphertext_is_bound_to_its_connection(other):
    """AAD = provider:workspace:connection — чужой шифротекст не подставить в другое подключение."""
    with pytest.raises(TokenDecryptError):
        decrypt(keys(), other, encrypt(keys(), REF, ACCESS, REFRESH))


@pytest.mark.parametrize("tamper", [
    lambda b: b[:3] + bytes([b[3] ^ 1]) + b[4:],           # nonce
    lambda b: b[:-1] + bytes([b[-1] ^ 1]),                 # тег
    lambda b: b[:20] + bytes([b[20] ^ 1]) + b[21:],        # шифротекст
    lambda b: b[:10],                                      # обрезан
    lambda b: bytes([2]) + b[1:],                          # неизвестный формат
])
def test_modified_envelope_is_rejected(tamper):
    with pytest.raises(TokenDecryptError):
        decrypt(keys(), REF, tamper(encrypt(keys(), REF, ACCESS, REFRESH)))


def test_wrong_or_unknown_key_version_is_rejected():
    blob = encrypt(keys(), REF, ACCESS, REFRESH)
    as_v2 = blob[:1] + (2).to_bytes(2, "big") + blob[3:]
    with pytest.raises(TokenDecryptError):
        decrypt(keys(current=2, versions=(1, 2)), REF, as_v2)       # версия есть, но ключ не тот
    with pytest.raises(TokenDecryptError, match="unknown key version"):
        decrypt(keys(), REF, as_v2)                                   # версии нет


def test_rotation_reads_old_writes_current():
    old = encrypt(keys(), REF, ACCESS, REFRESH)
    rotated = keys(current=2, versions=(1, 2))
    assert decrypt(rotated, REF, old).key_version == 1                 # старые записи читаются во время ротации
    again = decrypt(rotated, REF, encrypt(rotated, REF, ACCESS, REFRESH))
    assert (again.access_token, again.key_version) == (ACCESS, 2)     # запись — всегда текущим ключом


def test_secrets_never_in_repr_or_errors():
    stored = decrypt(keys(), REF, encrypt(keys(), REF, ACCESS, REFRESH))
    texts = [repr(stored), repr(Tokens(ACCESS, REFRESH, NOW))]
    try:
        decrypt(keys(), ConnectionRef("direct", 7, 43), encrypt(keys(), REF, ACCESS, REFRESH))
    except TokenDecryptError as e:
        texts.append(str(e))
    assert not any(secret in t for t in texts for secret in (ACCESS, REFRESH))


def test_key_config_errors():
    with pytest.raises(RuntimeError, match="текущей версии"):
        EnvKeys({"TOKEN_ENCRYPTION_KEY_1": base64.b64encode(b"k" * 32).decode(), "TOKEN_ENCRYPTION_KEY_VERSION": "2"})
    with pytest.raises(RuntimeError, match="32 байта"):
        EnvKeys({"TOKEN_ENCRYPTION_KEY_1": base64.b64encode(b"short").decode(), "TOKEN_ENCRYPTION_KEY_VERSION": "1"})


# --- Хранение в БД ----------------------------------------------------------------------------------

@pytest.fixture
def ref(rw, chain):
    cid = connected(rw, "direct", chain["ws"], f"crypto{chain['ws']}")
    r = ConnectionRef("direct", chain["ws"], cid)
    store(rw, keys(), r, Tokens(ACCESS, REFRESH, NOW + timedelta(days=365)))  # колбэк подключения — роль приложения
    return r


def test_stored_encrypted_and_read_only_by_worker(ref, token_role):
    blob = bytes(one(token_role, "SELECT connection_token('direct', %s, %s)", ref.workspace_id, ref.connection_id))
    assert ACCESS.encode() not in blob and REFRESH.encode() not in blob
    assert load(token_role, keys(), ref).access_token == ACCESS


def test_ciphertext_copied_to_other_connection_does_not_decrypt(rw, chain, ref, token_role):
    other = ConnectionRef("direct", chain["ws"], connected(rw, "direct", chain["ws"], f"other{chain['ws']}"))
    blob = one(token_role, "SELECT connection_token('direct', %s, %s)", ref.workspace_id, ref.connection_id)
    token_role.execute("SELECT set_connection_token('direct', %s, %s, %s, NULL)",
                       (other.workspace_id, other.connection_id, blob))
    with pytest.raises(TokenDecryptError):
        load(token_role, keys(), other)


# --- Обновление пары --------------------------------------------------------------------------------

class RotatingYandex:
    """Яндекс с ротацией refresh-токена: после обмена старый refresh недействителен."""

    def __init__(self, current=REFRESH, return_refresh=True, delay=0.0):
        self.current, self.return_refresh, self.delay, self.calls = current, return_refresh, delay, 0
        self._lock = threading.Lock()

    def __call__(self, request):
        form = parse_qs(request.content.decode())
        time.sleep(self.delay)
        with self._lock:
            self.calls += 1
            if form["refresh_token"][0] != self.current:
                return httpx.Response(400, json={"error": "invalid_grant"})
            self.current = f"refresh-{self.calls}"
            body = {"access_token": f"access-{self.calls}", "expires_in": 31536000}
            return httpx.Response(200, json={**body, "refresh_token": self.current} if self.return_refresh else body)


def fresh(conn, fake, ref, now=NOW, k=None):
    return fresh_access_token(conn, httpx.Client(transport=httpx.MockTransport(fake)), API_APP, k or keys(), ref, now)


def expire_soon(rw, ref):
    store(rw, keys(), ref, Tokens(ACCESS, REFRESH, NOW + timedelta(days=1)))


def test_valid_token_is_used_without_calling_yandex(ref, token_role):
    fake = RotatingYandex()
    assert fresh(token_role, fake, ref) == ACCESS and fake.calls == 0


def test_expiring_token_is_refreshed_and_new_pair_stored(rw, ref, token_role):
    expire_soon(rw, ref)
    fake = RotatingYandex()
    rotated = keys(current=2, versions=(1, 2))
    assert fresh(token_role, fake, ref, k=rotated) == "access-1"
    stored = load(token_role, rotated, ref)
    assert (stored.refresh_token, stored.key_version) == ("refresh-1", 2)   # новый refresh сохранён, ключ текущий
    assert one(rw, "SELECT token_expires_at FROM direct_connections WHERE id = %s", ref.connection_id) == \
        NOW + timedelta(seconds=31536000)                                     # срок access — отдельно, в колонке


def test_refresh_without_new_refresh_token_keeps_old_one(rw, ref, token_role):
    expire_soon(rw, ref)
    fresh(token_role, RotatingYandex(return_refresh=False), ref)
    assert load(token_role, keys(), ref).refresh_token == REFRESH


def test_rejected_refresh_requires_reauthorization_and_keeps_ciphertext(rw, ref, token_role):
    expire_soon(rw, ref)
    with pytest.raises(ReauthorizationRequired):
        fresh(token_role, RotatingYandex(current="another"), ref)
    assert rw.execute("SELECT status, status_detail, has_token FROM direct_connections WHERE id = %s",
                      (ref.connection_id,)).fetchone() == ("token_expired", "refresh_rejected", True)


def test_parallel_refresh_calls_yandex_once(rw, ref, db):
    """Два воркера одновременно видят истекающий токен. Без блокировки второй пришёл бы со старым refresh после
    ротации и получил ложный invalid_grant."""
    expire_soon(rw, ref)
    fake, results = RotatingYandex(delay=0.3), []

    def worker():
        with db("app_token") as conn:
            results.append(fresh(conn, fake, ref))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == ["access-1", "access-1"] and fake.calls == 1


def test_disconnect_during_refresh_is_not_undone(rw, ref, db):
    """Пользователь отключил подключение, пока шёл запрос обновления к Яндексу: новая пара не должна вернуть
    токен и статус connected — отключение ждёт конца обновления и применяется после него."""
    expire_soon(rw, ref)
    fake = RotatingYandex(delay=0.5)

    def worker():
        with db("app_token") as conn:
            fresh(conn, fake, ref)

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.2)  # обновление уже под блокировкой и ждёт ответа Яндекса
    rw.execute("SELECT drop_connection_token('direct', %s, %s, 'disconnected')", (ref.workspace_id, ref.connection_id))
    t.join()
    assert rw.execute("SELECT status, has_token FROM direct_connections WHERE id = %s",
                      (ref.connection_id,)).fetchone() == ("disconnected", False)
