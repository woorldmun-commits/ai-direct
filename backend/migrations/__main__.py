"""Применить миграции: `cd backend && MIGRATION_DATABASE_URL=postgresql://app_migrator@host/db python -m migrations`.

DSN — роль-владелец схемы (app_migrator), только из переменной окружения: секреты в аргументах видны в списке
процессов. Роли кластера (app_rw, app_token, app_system, app_deleter) должны существовать заранее.
"""

import os
import sys

import psycopg

from migrations import MigrationError, migrate


def main() -> int:
    dsn = os.environ.get("MIGRATION_DATABASE_URL", "").strip()
    if not dsn:
        print("MIGRATION_DATABASE_URL не задан: нужен DSN роли app_migrator", file=sys.stderr)
        return 2
    try:
        with psycopg.connect(dsn) as conn:
            applied = migrate(conn)
    except (MigrationError, psycopg.Error) as e:
        print(f"миграции не применены: {e}", file=sys.stderr)
        return 1
    print("применено: " + (", ".join(applied) if applied else "ничего, схема актуальна"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
