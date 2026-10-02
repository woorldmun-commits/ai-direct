"""Доступ (D3): роль в организации + роль в workspace. owner/admin видят все workspace организации, member — только
свои; участник workspace — обязательно участник той же организации; у организации всегда есть owner."""

import itertools

import psycopg
import pytest

from app.tenancy import WorkspaceNotFound, enter_workspace, workspace_role
from test_schema import connected, one

_n = itertools.count(1)


def user(rw) -> int:
    return one(rw, "INSERT INTO users (email) VALUES (%s) RETURNING id", f"acc{next(_n)}@example.test")


def join_org(rw, usr, org, role):
    rw.execute("INSERT INTO organization_memberships (user_id, organization_id, org_role) VALUES (%s, %s, %s)",
               (usr, org, role))


def join_ws(rw, usr, ws, role):
    rw.execute("INSERT INTO workspace_memberships (user_id, workspace_id, ws_role) VALUES (%s, %s, %s)", (usr, ws, role))


@pytest.fixture
def org(rw):
    """Агентство: owner, admin, member (участник только клиента A, viewer); клиенты A и B."""
    ids = {"owner": user(rw), "admin": user(rw), "member": user(rw)}
    with rw.transaction():
        ids["org"] = one(rw, "INSERT INTO organizations (name, kind) VALUES ('Агентство', 'agency') RETURNING id")
        join_org(rw, ids["owner"], ids["org"], "owner")
    join_org(rw, ids["admin"], ids["org"], "admin")
    join_org(rw, ids["member"], ids["org"], "member")
    for name in ("a", "b"):
        ids[name] = one(rw, "INSERT INTO workspaces (organization_id, name) VALUES (%s, %s) RETURNING id",
                        ids["org"], f"Клиент {name}")
    join_ws(rw, ids["member"], ids["a"], "viewer")
    return ids


# --- эффективная роль: одна точка проверки -------------------------------------------------------

@pytest.mark.parametrize("who, ws, role", [
    ("owner", "a", "owner"), ("owner", "b", "owner"),
    ("admin", "a", "admin"), ("admin", "b", "admin"),
    ("member", "a", "viewer"),
    ("member", "b", None),          # member видит только свои workspace; в чужом — как будто его нет
])
def test_effective_role(rw, org, who, ws, role):
    assert workspace_role(rw, org[who], org[ws]) == role


def test_member_lists_only_own_workspaces(rw, org):
    assert rw.execute("SELECT workspace_id, role FROM user_workspaces(%s)", (org["member"],)).fetchall() == \
        [(org["a"], "viewer")]
    assert [r[0] for r in rw.execute("SELECT workspace_id FROM user_workspaces(%s)", (org["admin"],))] == \
        [org["a"], org["b"]]


def test_deactivated_user_has_no_access(rw, org):
    rw.execute("UPDATE users SET status = 'deactivated', deactivated_at = now() WHERE id = %s", (org["member"],))
    assert workspace_role(rw, org["member"], org["a"]) is None


def test_member_is_isolated_from_other_workspace(db, rw, org):
    """Прикладная роль: вход в чужой workspace — WorkspaceNotFound (404), в свой — видны только его строки."""
    connected(rw, "direct", org["a"], f"la{org['a']}")
    connected(rw, "direct", org["b"], f"lb{org['b']}")
    with db("app_rw") as app:
        with pytest.raises(WorkspaceNotFound), app.transaction():
            enter_workspace(app, org["member"], org["b"])
        with app.transaction():
            assert enter_workspace(app, org["member"], org["a"]) == "viewer"
            seen = {r[0] for r in app.execute("SELECT workspace_id FROM direct_connections")}
            assert seen == {org["a"]}
            assert one(app, "SELECT count(*) FROM workspaces WHERE id = %s", org["b"]) == 0
        # SET LOCAL кончился вместе с транзакцией запроса
        assert one(app, "SELECT count(*) FROM direct_connections") == 0


def test_role_check_needs_no_workspace_context(db, org):
    with db("app_rw") as app:  # до входа в workspace: только ответ «какая роль», без строк
        assert workspace_role(app, org["owner"], org["b"]) == "owner"
        assert one(app, "SELECT count(*) FROM workspaces") == 0


# --- членство: ограничения в БД ------------------------------------------------------------------

def test_workspace_membership_requires_organization_membership(rw, org):
    outsider = user(rw)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        join_ws(rw, outsider, org["a"], "approver")


def test_workspace_membership_only_in_own_organization(rw, org):
    """Участник организации X не становится участником workspace организации Y."""
    other = user(rw)
    with rw.transaction():
        y = one(rw, "INSERT INTO organizations (name, kind) VALUES ('Y', 'business') RETURNING id")
        join_org(rw, other, y, "owner")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        join_ws(rw, other, org["a"], "analyst")
    # организацию строки задаёт workspace, а не приложение: подменить её нельзя
    rw.execute("UPDATE workspace_memberships SET organization_id = %s WHERE user_id = %s", (y, org["member"]))
    assert one(rw, "SELECT organization_id FROM workspace_memberships WHERE user_id = %s", org["member"]) == org["org"]


def test_unknown_roles_are_rejected(rw, org):
    with pytest.raises(psycopg.errors.CheckViolation):
        join_ws(rw, org["admin"], org["b"], "owner")
    with pytest.raises(psycopg.errors.CheckViolation):
        join_org(rw, user(rw), org["org"], "approver")


def test_removing_from_organization_removes_workspace_memberships(rw, org):
    join_ws(rw, org["member"], org["b"], "analyst")
    rw.execute("DELETE FROM organization_memberships WHERE user_id = %s AND organization_id = %s",
               (org["member"], org["org"]))
    assert one(rw, "SELECT count(*) FROM workspace_memberships WHERE user_id = %s", org["member"]) == 0
    assert workspace_role(rw, org["member"], org["a"]) is None


# --- хотя бы один owner --------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "DELETE FROM organization_memberships WHERE user_id = %(owner)s AND organization_id = %(org)s",
    "UPDATE organization_memberships SET org_role = 'admin' WHERE user_id = %(owner)s AND organization_id = %(org)s",
])
def test_last_owner_cannot_leave(rw, org, sql):
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="at least one owner"):
        rw.execute(sql, org)
    assert workspace_role(rw, org["owner"], org["a"]) == "owner"


def test_ownership_can_be_transferred_in_one_transaction(rw, org):
    """Проверка — на COMMIT: понизить старого владельца раньше, чем повысить нового, внутри транзакции можно."""
    with rw.transaction():
        rw.execute("UPDATE organization_memberships SET org_role = 'admin' WHERE user_id = %s AND organization_id = %s",
                   (org["owner"], org["org"]))
        rw.execute("UPDATE organization_memberships SET org_role = 'owner' WHERE user_id = %s AND organization_id = %s",
                   (org["admin"], org["org"]))
    assert workspace_role(rw, org["admin"], org["b"]) == "owner"


def test_organization_cannot_be_created_without_owner(rw):
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="at least one owner"):
        rw.execute("INSERT INTO organizations (name, kind) VALUES ('Без владельца', 'business')")
