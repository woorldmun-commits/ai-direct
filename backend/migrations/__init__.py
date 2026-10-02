"""Миграции схемы PostgreSQL: упорядоченные SQL-файлы и журнал применённых версий в БД.

Версия — файл `versions/NNNN_имя.sql` или каталог `versions/NNNN_имя/` (его *.sql склеиваются по имени файла:
так большой снимок укладывается в файлы ≤ 500 строк). Каждая версия применяется в своей транзакции под
advisory-блокировкой, журнал — таблица `migrations.schema_migrations` (версия + sha256 содержимого). Уже применённую
версию с другим хэшем раннер отказывается запускать: выпущенная миграция неизменна. Правила — README.md рядом.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

VERSIONS = Path(__file__).parent / "versions"
RELEASED = Path(__file__).parent / "released.txt"
_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+$")
# Произвольная константа: один мигратор на БД одновременно.
_LOCK_KEY = 0x61695F646972  # "ai_dir"

# Журнал — в отдельной схеме владельца: гранты схемы public (GRANT ... ON ALL TABLES IN SCHEMA public, default
# privileges) его не задевают, у рабочих ролей нет USAGE на схему — журнал они не видят и не меняют.
JOURNAL = "migrations.schema_migrations"
_JOURNAL = f"""
CREATE SCHEMA IF NOT EXISTS migrations;
REVOKE ALL ON SCHEMA migrations FROM PUBLIC;
CREATE TABLE IF NOT EXISTS {JOURNAL} (
  version    text PRIMARY KEY,
  checksum   text NOT NULL CHECK (checksum ~ '^[0-9a-f]{{64}}$'),
  applied_at timestamptz NOT NULL DEFAULT now()
)
"""


class MigrationError(RuntimeError):
    """Расхождение между файлами миграций и журналом БД; ничего не применено."""


@dataclass(frozen=True)
class Migration:
    version: str  # «0001_baseline»
    files: tuple[Path, ...]

    @property
    def sql(self) -> str:
        return "".join(f.read_text(encoding="utf-8") for f in self.files)

    @property
    def checksum(self) -> str:
        h = hashlib.sha256()
        for f in self.files:
            h.update(f.read_bytes())
        return h.hexdigest()


def discover(root: Path = VERSIONS) -> list[Migration]:
    """Все версии по порядку номеров. Номера уникальны и идут подряд с 0001 — иначе MigrationError."""
    found = []
    for entry in sorted(root.iterdir()):
        if entry.name.startswith((".", "_")):
            continue
        stem = entry.stem if entry.is_file() else entry.name
        if not _NAME.match(stem) or (entry.is_file() and entry.suffix != ".sql"):
            raise MigrationError(f"неожиданный файл в versions/: {entry.name}")
        files = (entry,) if entry.is_file() else tuple(sorted(entry.glob("*.sql")))
        if not files:
            raise MigrationError(f"пустой каталог миграции: {entry.name}")
        found.append(Migration(stem, files))
    numbers = [int(m.version[:4]) for m in found]
    if numbers != list(range(1, len(found) + 1)):
        raise MigrationError(f"номера миграций должны идти подряд с 0001: {[m.version for m in found]}")
    return found


def released(path: Path = RELEASED) -> dict[str, str]:
    """Зафиксированные хэши выпущенных версий: строки «версия sha256», # — комментарий."""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            version, checksum = line.split()
            out[version] = checksum
    return out


def migrate(conn: psycopg.Connection, migrations: list[Migration] | None = None) -> list[str]:
    """Применяет недостающие версии; возвращает их список. Подключение — ролью-владельцем схемы (app_migrator)."""
    migrations = discover() if migrations is None else migrations
    applied_now = []
    for m in migrations:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
            conn.execute(_JOURNAL)
            journal = dict(conn.execute(f"SELECT version, checksum FROM {JOURNAL}").fetchall())
            unknown = set(journal) - {x.version for x in migrations}
            if unknown:
                raise MigrationError(f"в БД есть версии, которых нет в файлах: {sorted(unknown)}")
            if m.version in journal:
                if journal[m.version] != m.checksum:
                    raise MigrationError(f"миграция {m.version} изменена после применения: выпущенные миграции неизменны")
                continue
            conn.execute(m.sql)
            conn.execute(f"INSERT INTO {JOURNAL} (version, checksum) VALUES (%s, %s)", (m.version, m.checksum))
            applied_now.append(m.version)
    return applied_now
