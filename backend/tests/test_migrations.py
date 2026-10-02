"""Миграции воспроизводят schema.sql: все версии на пустой БД дают тот же каталог, что и schema.sql.

Каталог сравнивается запросами к pg_catalog (без pg_dump: не нужен клиент той же версии, что сервер).
Расхождение = изменили schema.sql без миграции или наоборот (правило — migrations/README.md).
"""

import psycopg
import pytest
from conftest import SCHEMA, _admin_uri, _with_user

from migrations import JOURNAL, Migration, MigrationError, discover, migrate, released

FROM_MIGRATIONS = "ai_direct_mig_files"
FROM_SCHEMA = "ai_direct_mig_schema"

# Категория → запрос; каждая строка результата — сравнимый кортеж. Схема журнала migrations исключена: её нет в schema.sql.
_SORTED_ACL = "(SELECT array_agg(a::text ORDER BY a::text) FROM unnest({}) AS a)"
CATALOG = {
    "schemas_and_extensions": f"""
        SELECT 'schema', nspname, nspowner::regrole::text, {_SORTED_ACL.format('nspacl')}
          FROM pg_namespace WHERE nspname !~ '^(pg_|information_schema$|migrations$)'
        UNION ALL SELECT 'extension', extname, extversion, NULL FROM pg_extension""",
    "relations": f"""
        SELECT c.relname, c.relkind, c.relowner::regrole::text, c.relrowsecurity, c.relforcerowsecurity,
               c.reloptions::text, {_SORTED_ACL.format('c.relacl')}
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'""",
    "columns": f"""
        SELECT c.relname, row_number() OVER (PARTITION BY c.oid ORDER BY a.attnum), a.attname,
               format_type(a.atttypid, a.atttypmod), a.attnotnull, pg_get_expr(d.adbin, d.adrelid),
               a.attidentity, a.attgenerated, a.attcollation::regcollation::text, {_SORTED_ACL.format('a.attacl')}
          FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
          LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
         WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
           AND a.attnum > 0 AND NOT a.attisdropped""",
    "constraints": """
        SELECT coalesce(conrelid::regclass::text, contypid::regtype::text), conname, contype,
               pg_get_constraintdef(oid), condeferrable, condeferred, convalidated
          FROM pg_constraint WHERE connamespace = 'public'::regnamespace""",
    "indexes": "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'",
    "functions": f"""
        SELECT p.oid::regprocedure::text, p.prokind, p.proowner::regrole::text,
               CASE WHEN p.prokind IN ('f', 'p') THEN pg_get_functiondef(p.oid) END,
               {_SORTED_ACL.format('p.proacl')}
          FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace""",
    "triggers": """
        SELECT t.tgrelid::regclass::text, t.tgname, pg_get_triggerdef(t.oid), t.tgenabled FROM pg_trigger t
          JOIN pg_class c ON c.oid = t.tgrelid WHERE NOT t.tgisinternal AND c.relnamespace = 'public'::regnamespace""",
    "policies": """
        SELECT tablename, policyname, permissive, roles::text, cmd, qual, with_check
          FROM pg_policies WHERE schemaname = 'public'""",
    "views": "SELECT viewname, viewowner, definition FROM pg_views WHERE schemaname = 'public'",
    "types": """
        SELECT t.typname, t.typtype, format_type(t.typbasetype, t.typtypmod), t.typnotnull,
               (SELECT array_agg(e.enumlabel ORDER BY e.enumsortorder) FROM pg_enum e WHERE e.enumtypid = t.oid)
          FROM pg_type t LEFT JOIN pg_class c ON c.oid = t.typrelid
         WHERE t.typnamespace = 'public'::regnamespace AND t.typtype IN ('e', 'd', 'c', 'r')
           AND (c.oid IS NULL OR c.relkind = 'c')""",
    "sequences": """
        SELECT sequencename, data_type::text, start_value, increment_by, max_value, cycle
          FROM pg_sequences WHERE schemaname = 'public'""",
    "default_privileges": f"""
        SELECT d.defaclrole::regrole::text, coalesce(n.nspname, ''), d.defaclobjtype, {_SORTED_ACL.format('d.defaclacl')}
          FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace""",
    "comments": """
        SELECT c.relname, d.objsubid, d.description FROM pg_description d
          JOIN pg_class c ON d.classoid = 'pg_class'::regclass AND d.objoid = c.oid
         WHERE c.relnamespace = 'public'::regnamespace""",
}


def _create_db(admin: str, name: str) -> None:
    """Пустая БД так же, как в conftest: владелец app_migrator, рабочим ролям — USAGE на public."""
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {name}")
        conn.execute(f"CREATE DATABASE {name} OWNER app_migrator")
    with psycopg.connect(_with_user(admin, "postgres", name), autocommit=True) as conn:
        conn.execute("GRANT CREATE, USAGE ON SCHEMA public TO app_migrator")
        conn.execute("GRANT USAGE ON SCHEMA public TO app_rw, app_token, app_system, app_deleter")


def catalog(conn: psycopg.Connection) -> dict[str, list[tuple]]:
    return {name: sorted(conn.execute(sql).fetchall(), key=repr) for name, sql in CATALOG.items()}


@pytest.fixture(scope="module")
def dbs(db):  # db — роли кластера создаёт conftest
    admin = _admin_uri()
    for name in (FROM_MIGRATIONS, FROM_SCHEMA):
        _create_db(admin, name)
    with psycopg.connect(_with_user(admin, "app_migrator", FROM_SCHEMA), autocommit=True) as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
    with psycopg.connect(_with_user(admin, "app_migrator", FROM_MIGRATIONS)) as conn:
        applied = migrate(conn)
    assert applied == [m.version for m in discover()]

    def connect(name: str, role: str = "app_migrator") -> psycopg.Connection:
        return psycopg.connect(_with_user(admin, role, name), autocommit=True)

    return connect


@pytest.fixture(scope="module")
def catalogs(dbs) -> dict[str, dict[str, list[tuple]]]:
    out = {}
    for name in (FROM_MIGRATIONS, FROM_SCHEMA):
        with dbs(name) as conn:
            out[name] = catalog(conn)
    return out


@pytest.mark.parametrize("category", CATALOG)
def test_migrations_reproduce_schema_sql(catalogs, category):
    from_migrations, from_schema = catalogs[FROM_MIGRATIONS][category], catalogs[FROM_SCHEMA][category]
    only_migrations = [r for r in from_migrations if r not in from_schema]
    only_schema = [r for r in from_schema if r not in from_migrations]
    assert not only_migrations and not only_schema, (
        f"{category}: миграции и schema.sql расходятся — нужна новая миграция или правка schema.sql "
        f"(migrations/README.md).\nтолько в миграциях: {only_migrations}\nтолько в schema.sql: {only_schema}"
    )


def test_catalog_is_not_empty(catalogs):
    """Сравнение не вырождено: в схеме есть таблицы, функции, политики и гранты."""
    snap = catalogs[FROM_SCHEMA]
    for category in ("relations", "columns", "constraints", "indexes", "functions", "triggers", "policies"):
        assert snap[category], category
    assert any(row[-1] for row in snap["relations"]), "гранты на таблицы не попали в сравнение"


def test_released_migrations_are_frozen():
    """Каждая версия зафиксирована в released.txt, и её содержимое не менялось после выпуска."""
    frozen = released()
    on_disk = {m.version: m.checksum for m in discover()}
    missing = {v: c for v, c in on_disk.items() if v not in frozen}
    assert not missing, f"добавьте в migrations/released.txt: {missing}"
    assert set(frozen) <= set(on_disk), f"в released.txt есть версии без файлов: {set(frozen) - set(on_disk)}"
    changed = [v for v, c in frozen.items() if on_disk[v] != c]
    assert not changed, f"выпущенные миграции изменены: {changed} — изменение схемы оформляется новой миграцией"


def test_rerun_applies_nothing(dbs):
    with dbs(FROM_MIGRATIONS) as conn:
        assert migrate(conn) == []
        versions = [r[0] for r in conn.execute(f"SELECT version FROM {JOURNAL} ORDER BY version")]
    assert versions == [m.version for m in discover()]


def test_changed_applied_migration_is_refused(dbs, tmp_path):
    first = discover()[0]
    tampered = tmp_path / "01.sql"
    tampered.write_text(first.sql + "\n-- правка задним числом\n", encoding="utf-8")
    with dbs(FROM_MIGRATIONS) as conn, pytest.raises(MigrationError, match="изменена"):
        migrate(conn, [Migration(first.version, (tampered,)), *discover()[1:]])


def test_unknown_applied_version_is_refused(dbs):
    """В БД версия новее файлов (откат кода без отката схемы) — раннер не продолжает молча."""
    with dbs(FROM_MIGRATIONS) as conn, pytest.raises(MigrationError, match="нет в файлах"):
        with conn.transaction(force_rollback=True):  # лишняя запись журнала не переживает тест
            conn.execute(f"INSERT INTO {JOURNAL} VALUES ('9999_future', repeat('0', 64))")
            migrate(conn)


@pytest.mark.parametrize("role", ["app_rw", "app_token", "app_system", "app_deleter"])
def test_work_roles_cannot_read_or_write_journal(dbs, role):
    with dbs(FROM_MIGRATIONS, role) as conn:
        for sql in (f"SELECT * FROM {JOURNAL}", f"INSERT INTO {JOURNAL} VALUES ('9999_x', repeat('0', 64))"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(sql)


@pytest.mark.parametrize(
    "names, error",
    [
        (["0001_a.sql", "0003_c.sql"], "подряд"),
        (["0001_a.sql", "0001_b.sql"], "подряд"),
        (["0001_A.sql"], "неожиданный"),
        (["0001_a.txt"], "неожиданный"),
    ],
)
def test_discover_rejects_bad_layout(tmp_path, names, error):
    for name in names:
        (tmp_path / name).write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(MigrationError, match=error):
        discover(tmp_path)


def test_discover_glues_directory_in_file_order(tmp_path):
    (tmp_path / "0001_base").mkdir()
    (tmp_path / "0001_base" / "02_b.sql").write_text("SELECT 2;\n", encoding="utf-8")
    (tmp_path / "0001_base" / "01_a.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "0002_next.sql").write_text("SELECT 3;\n", encoding="utf-8")
    found = discover(tmp_path)
    assert [m.version for m in found] == ["0001_base", "0002_next"]
    assert found[0].sql == "SELECT 1;\nSELECT 2;\n"
