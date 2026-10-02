"""Реестр юридических документов: версия → точный текст → sha256 (D16). Хэш в legal_acceptances.document_sha256
считается из файла текста этой версии, а не задаётся руками: доказательство «что именно видел пользователь».

Тексты лежат в app/legal/texts/<document>/<version>.<locale>.md. Сейчас это ЗАГЛУШКИ: текст утверждает юрист
(docs/LEGAL.md), здесь его не сочиняем. Опубликованную версию не правят — меняется текст, значит, новая версия
(иначе хэш старых принятий перестанет совпадать с файлом)."""

import hashlib
import ipaddress
from datetime import datetime
from functools import cache
from pathlib import Path

import psycopg

TEXTS = Path(__file__).parent / "texts"
DEFAULT_LOCALE = "ru-RU"
USER_AGENT_MAX = 256  # как CHECK в legal_acceptances

# Документ → опубликованные версии (дата редакции). Новая версия = новый файл текста + строка здесь.
VERSIONS: dict[str, tuple[str, ...]] = {
    "offer": ("2026-10-01",),
    "pd_consent": ("2026-10-01",),
    "marketing": ("2026-10-01",),
    "agency_client_mandate": ("2026-10-01",),
}
WORKSPACE_DOCUMENTS = frozenset({"agency_client_mandate"})  # принимаются по конкретному workspace клиента


class UnknownDocument(ValueError):
    """Документа, версии или языка нет в реестре — принять то, чего пользователь не мог видеть, нельзя."""


def text_path(document: str, version: str, locale: str = DEFAULT_LOCALE) -> Path:
    if version not in VERSIONS.get(document, ()):
        raise UnknownDocument(f"{document}@{version}")
    path = TEXTS / document / f"{version}.{locale}.md"
    if not path.is_file():
        raise UnknownDocument(f"{document}@{version} ({locale})")
    return path


@cache
def text_sha256(document: str, version: str, locale: str = DEFAULT_LOCALE) -> str:
    """sha256 байтов файла текста (hex, 64 символа) — ровно то, что пишется в document_sha256."""
    return hashlib.sha256(text_path(document, version, locale).read_bytes()).hexdigest()


def is_published(document: str, version: str, locale: str = DEFAULT_LOCALE) -> bool:
    try:
        text_path(document, version, locale)
    except UnknownDocument:
        return False
    return True


def _ip(ip: str | None) -> str | None:
    return None if ip is None else str(ipaddress.ip_address(ip))  # ValueError на мусоре — до записи в БД


def _user_agent(user_agent: str | None) -> str | None:
    return user_agent[:USER_AGENT_MAX] if user_agent else None


def record_acceptance(conn: psycopg.Connection, *, user_id: int, document: str, version: str, accepted_at: datetime,
                      locale: str = DEFAULT_LOCALE, ip: str | None = None, user_agent: str | None = None,
                      workspace_id: int | None = None) -> None:
    """Одна строка legal_acceptances (append-only). Хэш — из реестра; мандат агентства — только с workspace_id
    (и в своём workspace: RLS прикладной роли, право owner/admin агентства — триггер БД)."""
    if (document in WORKSPACE_DOCUMENTS) != (workspace_id is not None):
        raise ValueError(f"{document}: workspace_id {'обязателен' if workspace_id is None else 'не нужен'}")
    conn.execute("""INSERT INTO legal_acceptances (user_id, document, version, accepted_at, document_sha256, locale,
                                                   ip, user_agent, workspace_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                 (user_id, document, version, accepted_at, text_sha256(document, version, locale), locale,
                  _ip(ip), _user_agent(user_agent), workspace_id))
