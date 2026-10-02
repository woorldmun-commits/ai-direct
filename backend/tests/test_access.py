"""Доступ (D3): роль в организации + роль в workspace. owner/admin видят все workspace организации, member — только
свои; участник workspace — обязательно участник той же организации; у организации всегда есть owner. Команду
меняют только функции с проверкой actor (owner/admin); у прикладной роли прямых прав на это нет."""

import itertools

import psycopg
import pytest

from app.tenancy import WorkspaceNotFound, enter_workspace, workspace_role
from test_schema import connected, one

_n = itertools.count(1)


def user(rw) -> int:
    return one(rw, "INSERT INTO users (email) VALUES (%s) RETURNING id", f"acc{next(_n)}@example.test")


def set_org(conn, actor, org, usr, role):
    conn.execute("SELECT set_organization_member(%s, %s, %s, %s)", (actor, org, usr, role))


def set_ws(conn, actor, ws, usr, role):
    conn.execute("SELECT set_workspace_member(%s, %s, %s, %s)", (actor, ws, usr, role))


@pytest.fixture
def org(rw):
    """Агентство: owner, admin, member (участник только клиента A, viewer); клиенты A и B."""
    ids = {"owner": user(rw), "admin": user(rw), "member": user(rw)}
    ids["org"] = one(rw, "SELECT create_organization(%s, 'Агентство', 'agency')", ids["owner"])
    set_org(rw, ids["owner"], ids["org"], ids["admin"], "admin")
    set_org(rw, ids["owner"], ids["org"], ids["member"], "member")
    for name in ("a", "b"):
        ids[name] = one(rw, "SELECT create_workspace(%s, %s, %s)", ids["owner"], ids["org"], f"Клиент {name}")
    set_ws(rw, ids["owner"], ids["a"], ids["member"], "viewer")
    return ids


@pytest.fixture
def app(db):
    with db("app_rw") as conn:
        yield conn


# --- эффективная роль: одна точка проверки -------------------------------------------------------

@pytest.mark.parametrize("who, ws, role", [
    ("owner", "a", "owner"), ("owner", "b", "owner"),
    ("admin", "a", "admin"), ("admin", "b", "admin"),
    ("member", "a", "viewer"),
    ("member", "b", None),          # member видит только свои workspace; в чужом — как будто его нет
])
def test_effective_role(rw, org, who, ws, role):
    assert workspace_role(rw, org[who], org[ws]) == role


def test_member_lists_only_own_workspaces(app, org):
    """Список workspace — user_workspaces (SECURITY DEFINER), без организационного контекста RLS."""
    assert app.execute("SELECT workspace_id, role FROM user_workspaces(%s)", (org["member"],)).fetchall() == \
        [(org["a"], "viewer")]
    assert [r[0] for r in app.execute("SELECT workspace_id FROM user_workspaces(%s)", (org["admin"],))] == \
        [org["a"], org["b"]]


def test_deactivated_user_has_no_access(rw, org):
    rw.execute("UPDATE users SET status = 'deactivated', deactivated_at = now() WHERE id = %s", (org["member"],))
    assert workspace_role(rw, org["member"], org["a"]) is None


def test_member_is_isolated_from_other_workspace(app, rw, org):
    """Прикладная роль: вход в чужой workspace — WorkspaceNotFound (404), в свой — видны только его строки."""
    connected(rw, "direct", org["a"], f"la{org['a']}")
    connected(rw, "direct", org["b"], f"lb{org['b']}")
    with pytest.raises(WorkspaceNotFound), app.transaction():
        enter_workspace(app, org["member"], org["b"])
    with app.transaction():
        assert enter_workspace(app, org["member"], org["a"]) == "viewer"
        seen = {r[0] for r in app.execute("SELECT workspace_id FROM direct_connections")}
        assert seen == {org["a"]}
        assert one(app, "SELECT count(*) FROM workspaces WHERE id = %s", org["b"]) == 0
    # SET LOCAL кончился вместе с транзакцией запроса
    assert one(app, "SELECT count(*) FROM direct_connections") == 0


def test_role_check_needs_no_workspace_context(app, org):
    # до входа в workspace: только ответ «какая роль», без строк
    assert workspace_role(app, org["owner"], org["b"]) == "owner"
    assert one(app, "SELECT count(*) FROM workspaces") == 0


def test_organization_context_opens_nothing(app, org):
    """Организационного контекста больше нет: app.organization_id ничего не открывает и не даёт писать."""
    with app.transaction():
        app.execute("SELECT set_config('app.organization_id', %s, true)", (str(org["org"]),))
        assert one(app, "SELECT count(*) FROM workspaces") == 0
        assert one(app, "SELECT count(*) FROM workspace_memberships") == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege), app.transaction():
            app.execute("""INSERT INTO workspace_memberships (user_id, workspace_id, ws_role)
                           SELECT user_id, %s, 'approver' FROM organization_memberships WHERE organization_id = %s""",
                        (org["b"], org["org"]))


# --- управление командой: только функции, только owner/admin -------------------------------------

@pytest.mark.parametrize("sql", [
    "INSERT INTO workspace_memberships (user_id, workspace_id, ws_role) VALUES (%(member)s, %(b)s, 'approver')",
    "UPDATE workspace_memberships SET ws_role = 'approver' WHERE user_id = %(member)s",
    "DELETE FROM workspace_memberships WHERE user_id = %(member)s",
    "INSERT INTO organization_memberships (user_id, organization_id, org_role) VALUES (%(admin)s, %(org)s, 'owner')",
    "UPDATE organization_memberships SET org_role = 'owner' WHERE user_id = %(member)s",
    "DELETE FROM organization_memberships WHERE user_id = %(member)s",
    "INSERT INTO organizations (name, kind) VALUES ('x', 'business')",
    "UPDATE organizations SET name = 'x' WHERE id = %(org)s",
    "DELETE FROM organizations WHERE id = %(org)s",
    "INSERT INTO workspaces (organization_id, name) VALUES (%(org)s, 'x')",
    "UPDATE workspaces SET organization_id = %(org)s WHERE id = %(a)s",
])
@pytest.mark.parametrize("role", ["app_rw", "app_token", "app_system"])
def test_app_roles_cannot_change_team_directly(db, org, role, sql):
    with db(role) as conn, conn.transaction():
        conn.execute("SELECT set_config('app.workspace_id', %s, true)", (str(org["a"]),))
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="permission denied"):
            conn.execute(sql, org)


def test_member_cannot_change_memberships(app, org):
    outsider = user(app)
    for call in (lambda: set_ws(app, org["member"], org["a"], org["member"], "approver"),   # повысить себя
                 lambda: set_ws(app, org["member"], org["b"], org["member"], "viewer"),     # войти в чужой
                 lambda: set_org(app, org["member"], org["org"], outsider, "member"),
                 lambda: set_org(app, org["member"], org["org"], org["member"], "admin"),
                 lambda: app.execute("SELECT remove_workspace_member(%s, %s, %s)",
                                     (org["member"], org["a"], org["member"])),
                 lambda: app.execute("SELECT remove_organization_member(%s, %s, %s)",
                                     (org["member"], org["org"], org["admin"])),
                 lambda: app.execute("SELECT create_workspace(%s, %s, 'x')", (org["member"], org["org"]))):
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="cannot manage"):
            call()
    assert workspace_role(app, org["member"], org["a"]) == "viewer"
    assert workspace_role(app, org["member"], org["b"]) is None


def test_admin_manages_team(app, org):
    newcomer = user(app)
    set_org(app, org["admin"], org["org"], newcomer, "member")
    set_ws(app, org["admin"], org["b"], newcomer, "analyst")
    assert workspace_role(app, newcomer, org["b"]) == "analyst"
    set_ws(app, org["admin"], org["b"], newcomer, "approver")  # смена роли
    assert workspace_role(app, newcomer, org["b"]) == "approver"
    app.execute("SELECT remove_workspace_member(%s, %s, %s)", (org["admin"], org["b"], newcomer))
    assert workspace_role(app, newcomer, org["b"]) is None
    ws = one(app, "SELECT create_workspace(%s, %s, 'Клиент C')", org["admin"], org["org"])
    assert workspace_role(app, org["owner"], ws) == "owner"


def test_only_owner_manages_owners(app, org):
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="owner"):
        set_org(app, org["admin"], org["org"], org["member"], "owner")
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="owner"):
        set_org(app, org["admin"], org["org"], org["owner"], "member")
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="owner"):
        app.execute("SELECT remove_organization_member(%s, %s, %s)", (org["admin"], org["org"], org["owner"]))
    set_org(app, org["owner"], org["org"], org["admin"], "owner")
    assert workspace_role(app, org["admin"], org["a"]) == "owner"


def test_deactivated_admin_cannot_manage(rw, app, org):
    rw.execute("UPDATE users SET status = 'deactivated', deactivated_at = now() WHERE id = %s", (org["admin"],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        set_ws(app, org["admin"], org["b"], org["member"], "viewer")


def test_unknown_workspace_is_not_manageable(app, org):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        set_ws(app, org["owner"], 10**12, org["member"], "viewer")


# --- членство: ограничения в БД ------------------------------------------------------------------

def test_workspace_membership_requires_organization_membership(app, org):
    outsider = user(app)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        set_ws(app, org["owner"], org["a"], outsider, "approver")


def test_workspace_membership_only_in_own_organization(db, app, org):
    """Участник организации X не становится участником workspace организации Y."""
    other = user(app)
    y = one(app, "SELECT create_organization(%s, 'Y', 'business')", other)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):  # owner Y не управляет workspace организации X
        set_ws(app, other, org["a"], other, "analyst")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):    # и owner X не добавит в workspace не своего участника
        set_ws(app, org["owner"], org["a"], other, "analyst")
    # организацию строки задаёт workspace, а не вызывающий: подменить её нельзя даже владельцу таблиц
    with db("app_migrator") as owner:
        owner.execute("UPDATE workspace_memberships SET organization_id = %s WHERE user_id = %s", (y, org["member"]))
    assert one(app, "SELECT organization_id FROM user_workspaces(%s)", org["member"]) == org["org"]


def test_workspace_cannot_move_to_another_organization(db, rw, org):
    """organization_id неизменяем: даже у владельца таблиц — триггер; у приложения — нет права на столбец."""
    y = one(rw, "SELECT create_organization(%s, 'Y2', 'business')", user(rw))
    with db("app_migrator") as owner, pytest.raises(psycopg.errors.InsufficientPrivilege, match="immutable"):
        owner.execute("UPDATE workspaces SET organization_id = %s WHERE id = %s", (y, org["a"]))
    with db("app_rw") as app, app.transaction():
        app.execute("SELECT set_config('app.workspace_id', %s, true)", (str(org["a"]),))
        with pytest.raises(psycopg.errors.InsufficientPrivilege), app.transaction():
            app.execute("UPDATE workspaces SET organization_id = %s WHERE id = %s", (y, org["a"]))
        app.execute("UPDATE workspaces SET name = 'Клиент А' WHERE id = %s", (org["a"],))  # название — можно
    assert workspace_role(rw, org["owner"], org["a"]) == "owner"


def test_unknown_roles_are_rejected(app, org):
    with pytest.raises(psycopg.errors.CheckViolation):
        set_ws(app, org["owner"], org["b"], org["admin"], "owner")
    with pytest.raises(psycopg.errors.CheckViolation):
        set_org(app, org["owner"], org["org"], user(app), "approver")


def test_removing_from_organization_removes_workspace_memberships(app, org):
    set_ws(app, org["owner"], org["b"], org["member"], "analyst")
    app.execute("SELECT remove_organization_member(%s, %s, %s)", (org["owner"], org["org"], org["member"]))
    assert workspace_role(app, org["member"], org["a"]) is None
    assert workspace_role(app, org["member"], org["b"]) is None


# --- хотя бы один owner --------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "SELECT remove_organization_member(%(owner)s, %(org)s, %(owner)s)",
    "SELECT set_organization_member(%(owner)s, %(org)s, %(owner)s, 'admin')",
])
def test_last_owner_cannot_leave(app, org, sql):
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="at least one owner"):
        app.execute(sql, org)
    assert workspace_role(app, org["owner"], org["a"]) == "owner"


def test_ownership_can_be_transferred_in_one_transaction(db, rw, org):
    """Проверка — на COMMIT: понизить старого владельца раньше, чем повысить нового, внутри транзакции можно
    (прямые UPDATE — у владельца таблиц; приложение передаёт владение функциями: сначала повысить, потом уйти)."""
    with db("app_migrator") as owner, owner.transaction():
        owner.execute("UPDATE organization_memberships SET org_role = 'admin' WHERE user_id = %s AND organization_id = %s",
                      (org["owner"], org["org"]))
        owner.execute("UPDATE organization_memberships SET org_role = 'owner' WHERE user_id = %s AND organization_id = %s",
                      (org["admin"], org["org"]))
    assert workspace_role(rw, org["admin"], org["b"]) == "owner"


def test_organization_cannot_be_created_without_owner(db):
    with db("app_migrator") as owner:
        with pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="at least one owner"):
            owner.execute("INSERT INTO organizations (name, kind) VALUES ('Без владельца', 'business')")


def test_two_owners_cannot_both_step_down_concurrently(db, org):
    """Гонка: два owner одновременно понижают себя. Строка организации обновляется в проверке (а не только
    блокируется) — в REPEATABLE READ вторая транзакция получает serialization_failure, а не организацию без owner."""
    with db("app_rw") as app:
        set_org(app, org["owner"], org["org"], org["admin"], "owner")
    for level in (psycopg.IsolationLevel.REPEATABLE_READ, psycopg.IsolationLevel.READ_COMMITTED):
        with db("app_rw") as c1, db("app_rw") as c2:
            for c in (c1, c2):
                c.autocommit = False
                c.isolation_level = level
            set_org(c1, org["owner"], org["org"], org["owner"], "member")
            set_org(c2, org["admin"], org["org"], org["admin"], "member")
            c1.commit()
            with pytest.raises((psycopg.errors.SerializationFailure, psycopg.errors.IntegrityConstraintViolation)):
                c2.commit()
        with db("app_rw") as app:
            owners = one(app, "SELECT count(*) FROM organization_memberships WHERE organization_id = %s "
                              "AND org_role = 'owner'", org["org"])
            assert owners == 1
            # вернуть второго owner для следующего уровня изоляции
            remaining = one(app, "SELECT user_id FROM organization_memberships WHERE organization_id = %s "
                                 "AND org_role = 'owner'", org["org"])
            other = org["admin"] if remaining == org["owner"] else org["owner"]
            set_org(app, remaining, org["org"], other, "owner")
