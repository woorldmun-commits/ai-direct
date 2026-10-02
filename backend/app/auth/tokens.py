"""Токены подключений Директа и Метрики (API-приложение): шифрование, хранение, обновление.

Конверт в *_connections.token_enc — один bytea: формат (1 байт) · key_version (2 байта) · nonce (12) · AES-GCM
шифротекст+тег. Внутри — пара access+refresh (JSON): одна запись, поэтому замена пары после refresh атомарна.
AAD = provider:workspace_id:connection_id — шифротекст одного подключения не расшифруется в другом.

Ключи — KeyProvider: сейчас переменные окружения, позже Yandex Lockbox без изменений в этом модуле. В БД — только
версия ключа внутри конверта. Ротация без остановки: читается любая известная версия, пишется всегда текущая —
старые записи перешифровываются при следующем refresh.

Шифротекст приложению (app_rw) недоступен: пишет функция set_connection_token, читает только роль app_token
(connection_token). Расшифрованный токен — только в полях с repr=False и не попадает в тексты исключений."""

import base64
import json
import os
import secrets
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Mapping, Protocol

import httpx
import psycopg
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.auth.yandex_oauth import OAuthApp, ReauthorizationRequired, Tokens, refresh
from app.tenancy import workspace_scope

FORMAT = 1
_HEADER = struct.Struct(">BH")  # формат, версия ключа
NONCE_BYTES = 12
REFRESH_BEFORE = timedelta(days=30)  # Яндекс советует обновлять долгоживущие токены раз в несколько месяцев


class TokenDecryptError(Exception):
    """Конверт не расшифровывается: чужое подключение, изменённые данные или неизвестный ключ. Без содержимого."""


class KeyProvider(Protocol):
    def current_version(self) -> int: ...
    def key(self, version: int) -> bytes: ...  # KeyError — версия неизвестна


class EnvKeys:
    """TOKEN_ENCRYPTION_KEY_VERSION — текущая версия; TOKEN_ENCRYPTION_KEY_<v> — ключи (base64, 32 байта).
    На время ротации заданы и старый, и новый ключ."""

    def __init__(self, env: Mapping[str, str] = os.environ):
        prefix = "TOKEN_ENCRYPTION_KEY_"
        self._keys = {int(k[len(prefix):]): base64.b64decode(v) for k, v in env.items()
                      if k.startswith(prefix) and k[len(prefix):].isdigit()}
        self._current = int(env.get("TOKEN_ENCRYPTION_KEY_VERSION", "0"))
        if self._current not in self._keys:
            raise RuntimeError("не задан ключ текущей версии: TOKEN_ENCRYPTION_KEY_VERSION / TOKEN_ENCRYPTION_KEY_<v>")
        if any(len(k) != 32 for k in self._keys.values()):
            raise RuntimeError("ключ шифрования токенов должен быть 32 байта (AES-256)")

    def current_version(self) -> int:
        return self._current

    def key(self, version: int) -> bytes:
        return self._keys[version]


@dataclass(frozen=True)
class ConnectionRef:
    kind: str  # direct · metrika
    workspace_id: int
    connection_id: int

    @property
    def aad(self) -> bytes:
        return f"{self.kind}:{self.workspace_id}:{self.connection_id}".encode()


@dataclass(frozen=True)
class StoredTokens:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    key_version: int


def encrypt(keys: KeyProvider, ref: ConnectionRef, access_token: str, refresh_token: str | None) -> bytes:
    version, nonce = keys.current_version(), secrets.token_bytes(NONCE_BYTES)
    plain = json.dumps({"access": access_token, "refresh": refresh_token}).encode()
    return _HEADER.pack(FORMAT, version) + nonce + AESGCM(keys.key(version)).encrypt(nonce, plain, ref.aad)


def decrypt(keys: KeyProvider, ref: ConnectionRef, blob: bytes) -> StoredTokens:
    if len(blob) <= _HEADER.size + NONCE_BYTES:
        raise TokenDecryptError("token envelope is truncated")
    fmt, version = _HEADER.unpack_from(blob)
    if fmt != FORMAT:
        raise TokenDecryptError(f"unknown token envelope format {fmt}")
    try:
        key = keys.key(version)
    except KeyError:
        raise TokenDecryptError(f"unknown key version {version}") from None
    nonce, body = blob[_HEADER.size:_HEADER.size + NONCE_BYTES], blob[_HEADER.size + NONCE_BYTES:]
    try:
        plain = json.loads(AESGCM(key).decrypt(nonce, body, ref.aad))
    except InvalidTag:
        raise TokenDecryptError(f"token of {ref.kind} connection {ref.connection_id} failed authentication") from None
    return StoredTokens(plain["access"], plain["refresh"], version)


def store(conn: psycopg.Connection, keys: KeyProvider, ref: ConnectionRef, tokens: Tokens) -> None:
    """OAuth-колбэк подключения и refresh: пара шифруется текущим ключом и заменяется одной записью."""
    conn.execute("SELECT set_connection_token(%s, %s, %s, %s, %s)",
                 (ref.kind, ref.workspace_id, ref.connection_id,
                  encrypt(keys, ref, tokens.access_token, tokens.refresh_token), tokens.expires_at))


def load(conn: psycopg.Connection, keys: KeyProvider, ref: ConnectionRef) -> StoredTokens:
    """Только роль app_token. Подключение ищется в пределах workspace: чужое — NoDataFound."""
    blob = conn.execute("SELECT connection_token(%s, %s, %s)",
                        (ref.kind, ref.workspace_id, ref.connection_id)).fetchone()[0]
    return decrypt(keys, ref, bytes(blob))


def fresh_access_token(conn: psycopg.Connection, http: httpx.Client, app: OAuthApp, keys: KeyProvider,
                       ref: ConnectionRef, now: datetime) -> str:
    """Действующий access-токен подключения; за REFRESH_BEFORE до истечения — обновляет пару.

    Обновление — под сессионной advisory-блокировкой подключения (вне транзакции: запрос к Яндексу в ней не держим).
    Под блокировкой срок перечитывается: если параллельный воркер уже обновил пару, к Яндексу не идём — иначе
    повтор со старым refresh-токеном после его ротации дал бы ложный invalid_grant.
    invalid_grant → статус token_expired (нужно переподключить), шифротекст остаётся; удаление токена — отдельное
    явное действие (drop_connection_token)."""
    assert conn.autocommit, "блокировка сессионная, HTTP вне транзакции: нужен autocommit"
    with workspace_scope(conn, ref.workspace_id):  # RLS: срок и статус подключения — только своего workspace
        return _fresh_access_token(conn, http, app, keys, ref, now)


def _fresh_access_token(conn: psycopg.Connection, http: httpx.Client, app: OAuthApp, keys: KeyProvider,
                        ref: ConnectionRef, now: datetime) -> str:
    lock = (f"token:{ref.kind}:{ref.connection_id}",)  # тот же ключ берёт drop_connection_token (schema.sql)
    conn.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", lock)
    try:
        stored = load(conn, keys, ref)
        expires_at = _expires_at(conn, ref)
        if expires_at is None or expires_at - now > REFRESH_BEFORE:  # None: Яндекс не сообщил срок
            return stored.access_token
        if not stored.refresh_token:
            _needs_reauthorization(conn, ref, "no_refresh_token")
        try:
            new = refresh(http, app, stored.refresh_token, now)
        except ReauthorizationRequired:
            _needs_reauthorization(conn, ref, "refresh_rejected")
        store(conn, keys, ref, Tokens(new.access_token, new.refresh_token or stored.refresh_token, new.expires_at))
        return new.access_token
    finally:
        conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", lock)


def _expires_at(conn: psycopg.Connection, ref: ConnectionRef) -> datetime | None:
    table = {"direct": "direct_connections", "metrika": "metrika_connections"}[ref.kind]
    return conn.execute(f"SELECT token_expires_at FROM {table} WHERE id = %s AND workspace_id = %s",
                        (ref.connection_id, ref.workspace_id)).fetchone()[0]


def _needs_reauthorization(conn: psycopg.Connection, ref: ConnectionRef, detail: str):
    table = {"direct": "direct_connections", "metrika": "metrika_connections"}[ref.kind]
    conn.execute(f"""UPDATE {table} SET status = 'token_expired', status_detail = %s, status_changed_at = now()
                     WHERE id = %s AND workspace_id = %s""", (detail, ref.connection_id, ref.workspace_id))
    raise ReauthorizationRequired(detail)
