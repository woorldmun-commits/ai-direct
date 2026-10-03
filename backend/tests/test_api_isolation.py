"""Изоляция на границе API (D13, API_CONTRACT.md §1, §10, §12) — на реальной БД, через HTTP.

actor — только из проверенной сессии; workspace — из пути и только через workspace_role → SET LOCAL; нет доступа —
404, неотличимый от несуществующего workspace; соединение возвращается в пул без контекста workspace."""

from datetime import timedelta

import pytest
from psycopg_pool import PoolTimeout

from app.api import create_app
from app.tenancy import enter_workspace
from test_api_support import (ORIGIN, api, client_for, cookie, pooled_workspace_setting, session,  # noqa: F401
                              settings, world, ws)


def body_without_request_id(r) -> dict:
    data = r.json()
    data["error"].pop("request_id")
    return data


def recs(api, token, ids, name, **params):
    return api.get(f"/api/v1/workspaces/{ws(ids, name)}/recommendations", headers=cookie(token), params=params)


# --- аутентификация: actor только из сессии ----------------------------------------------------------

@pytest.mark.parametrize("path", ["/api/v1/me", "/api/v1/workspaces/ws_1/recommendations",
                                  "/api/v1/workspaces/ws_1/members"])
def test_without_cookie_401(api, path):
    r = api.get(path)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"
    assert r.json()["error"]["request_id"] == r.headers["x-request-id"]


@pytest.mark.parametrize("token", ["garbage", "x" * 43, "a" * 500, "токен"])
def test_unknown_or_malformed_session_401(api, token):
    r = api.get("/api/v1/me", headers={"Cookie": f"session={token}"} if token.isascii() else {})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize("kind", ["revoked", "expired", "deactivated"])
def test_revoked_expired_or_deactivated_session_401(api, rw, world, kind):
    uid = world["viewer"]
    token = session(rw, uid, revoked=kind == "revoked",
                    expires_in=timedelta(minutes=-1) if kind == "expired" else timedelta(days=1))
    if kind == "deactivated":
        rw.execute("UPDATE users SET status = 'deactivated', deactivated_at = now() WHERE id = %s", (uid,))
    for path in ("/api/v1/me", f"/api/v1/workspaces/{ws(world, 'a1')}/recommendations"):
        r = api.get(path, headers=cookie(token))
        assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated", (kind, path)


def test_session_identifies_user(api, rw, world):
    r = api.get("/api/v1/me", headers=cookie(session(rw, world["viewer"])))
    assert r.status_code == 200 and r.json()["user"]["id"] == f"u_{world['viewer']}"


def test_actor_cannot_be_substituted_by_query_header_or_body(api, rw, world):
    """Пользователь сессии — viewer агентства A. Подсказки «я — owner B» в query, заголовках и теле не работают."""
    token = session(rw, world["viewer"])
    other = str(world["owner_b"])
    spoof = {"X-User-Id": other, "X-Actor-Id": other, "X-Forwarded-User": other, "X-Remote-User": other,
             "Authorization": f"Bearer {other}"}
    r = api.request("GET", "/api/v1/me", params={"user_id": other, "actor": other},
                    headers={**cookie(token), **spoof}, json={"user_id": other, "actor_user_id": other})
    assert r.status_code == 200
    me = r.json()
    assert me["user"]["id"] == f"u_{world['viewer']}"
    assert [o["id"] for o in me["organizations"]] == [f"org_{world['org_a']}"]
    # чужой workspace остаётся чужим с теми же подсказками
    r = api.get(f"/api/v1/workspaces/{ws(world, 'b1')}/recommendations", headers={**cookie(token), **spoof})
    assert r.status_code == 404
    # лишний параметр запроса — не подсказка, а ошибка формата
    r = recs(api, token, world, "a1", user_id=other)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"


def test_without_session_spoofed_actor_is_still_401(api, world):
    other = str(world["owner_b"])
    r = api.get("/api/v1/me", params={"user_id": other}, headers={"X-User-Id": other})
    assert r.status_code == 401


# --- доступ к workspace: 404, а не 403 ----------------------------------------------------------------

@pytest.mark.parametrize("who, target", [("owner", "b1"), ("admin", "b1"), ("viewer", "b1"), ("owner_b", "a1")])
def test_other_organization_is_404_like_nonexistent(api, rw, world, who, target):
    token = session(rw, world[who])
    for tail in ("recommendations", "members"):
        foreign = api.get(f"/api/v1/workspaces/{ws(world, target)}/{tail}", headers=cookie(token))
        missing = api.get(f"/api/v1/workspaces/ws_999999999/{tail}", headers=cookie(token))
        assert foreign.status_code == missing.status_code == 404
        assert body_without_request_id(foreign) == body_without_request_id(missing) == {
            "error": {"code": "not_found", "message": "Не найдено."}}


def test_member_without_workspace_membership_does_not_see_own_org_workspace(api, rw, world):
    """member организации A без workspace_membership — 404 даже в своей организации; viewer — только a1."""
    member = session(rw, world["member"])
    viewer = session(rw, world["viewer"])
    for name in ("a1", "a2"):
        assert recs(api, member, world, name).status_code == 404
    assert recs(api, viewer, world, "a2").status_code == 404
    assert recs(api, viewer, world, "a1").status_code == 200


@pytest.mark.parametrize("bad", ["1", "ws_", "ws_0", "ws_01", "ws_abc", "ws_99999999999999999999", "ws_1;--",
                                 "WS_1"])
def test_malformed_workspace_id_is_404(api, rw, world, bad):
    r = api.get(f"/api/v1/workspaces/{bad}/recommendations", headers=cookie(session(rw, world["owner"])))
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_viewer_reads_only_own_workspace_data(api, rw, world):
    r = recs(api, session(rw, world["viewer"]), world, "a1")
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["id"] for i in items] == [f"rec_{world['rec_a1']['rec']}"]
    text = r.text
    for foreign in ("rec_a2", "rec_b1"):  # ни id, ни логина, ни суммы чужого workspace
        assert f"rec_{world[foreign]['rec']}" not in text
        assert world[foreign]["login"] not in text
    assert "99999.00" not in text


def test_owner_sees_each_workspace_separately(api, rw, world):
    token = session(rw, world["owner"])
    a1 = recs(api, token, world, "a1").json()["items"]
    a2 = recs(api, token, world, "a2").json()["items"]
    assert [i["id"] for i in a1] == [f"rec_{world['rec_a1']['rec']}"]
    assert [i["id"] for i in a2] == [f"rec_{world['rec_a2']['rec']}"]


def test_recommendation_item_shape(api, rw, world):
    item = recs(api, session(rw, world["viewer"]), world, "a1").json()["items"][0]
    rec = world["rec_a1"]
    assert item["version_id"] == f"rv_{rec['finding']}"
    assert item["ad_account"] == {"id": f"acc_{rec['account']}", "login": rec["login"]}
    assert item["exposure"]["amount"] == "12500.00" and item["exposure"]["calculation_type"] == "estimated"
    assert item["exposure"]["period"] == {"from": "2026-09-22", "to": "2026-09-28"}
    assert "snapshot_id" not in item["exposure"] and "period_from" not in item["exposure"]
    assert item["can_save"]["amount"] is None and item["can_save"]["calculation_type"] == "unavailable"
    # can_save записан до 0004 без причины — API отдаёт её как no_data, а не выдумывает конкретную
    assert item["can_save"]["unavailable_reason"] == "no_data" and item["exposure"]["unavailable_reason"] is None
    assert item["action_level"] == "review" and item["object"]["type"] == "campaign"
    assert item["object"]["name"] is None  # названий кампаний в схеме нет — null, а не выдуманное
    # review, стратегия неизвестна: не «только ставка», а рычаги по стратегии (API_CONTRACT §5)
    assert item["action"]["type"] == "lower_cpa" and item["action"]["strategy"] == "unknown"
    assert {lv["lever"] for lv in item["action"]["levers"]} == {"decrease_bid", "lower_target_cpa",
                                                                 "check_conversion_goals"}
    assert item["title"] and item["status"] == "new"
    assert item["execution_mode"] is None and item["verification_status"] is None
    assert item["exposure_overlap"]["amount"] == "0.00" and item["data_sufficiency"] == "sufficient"
    assert item["computed_at"] is not None


def test_foreign_ad_account_filter_returns_nothing(api, rw, world):
    token = session(rw, world["owner"])
    r = recs(api, token, world, "a1", ad_account=f"acc_{world['rec_b1']['account']}")
    assert r.status_code == 200 and r.json()["items"] == []


def test_members_only_for_managers(api, rw, world):
    path = f"/api/v1/workspaces/{ws(world, 'a1')}/members"
    r = api.get(path, headers=cookie(session(rw, world["viewer"])))
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_role"
    r = api.get(path, headers=cookie(session(rw, world["admin"])))
    assert r.status_code == 200
    got = {m["user"]["id"]: (m["org_role"], m["ws_role"]) for m in r.json()["items"]}
    assert got == {f"u_{world['owner']}": ("owner", None), f"u_{world['admin']}": ("admin", None),
                   f"u_{world['viewer']}": ("member", "viewer")}  # member без роли в a1 — не участник a1
    assert f"u_{world['owner_b']}" not in r.text


def test_me_lists_effective_roles(api, rw, world):
    def me(who):
        return api.get("/api/v1/me", headers=cookie(session(rw, world[who]))).json()["organizations"]

    [owner] = me("owner")
    assert owner["org_role"] == "owner"
    assert [(w["id"], w["ws_role"]) for w in owner["workspaces"]] == [(ws(world, "a1"), None), (ws(world, "a2"), None)]
    assert [w["name"] for w in owner["workspaces"]] == ["Клиент a1", "Клиент a2"]
    [viewer] = me("viewer")
    assert viewer["org_role"] == "member"
    assert [(w["id"], w["ws_role"]) for w in viewer["workspaces"]] == [(ws(world, "a1"), "viewer")]
    [member] = me("member")
    assert member["workspaces"] == []
    [b] = me("owner_b")
    assert [w["id"] for w in b["workspaces"]] == [ws(world, "b1")]


# --- соединение пула без контекста workspace ----------------------------------------------------------

def test_pool_connection_has_no_workspace_after_request(api, rw, world):
    token = session(rw, world["owner"])
    for path, status in ((f"/api/v1/workspaces/{ws(world, 'a1')}/recommendations", 200),
                         (f"/api/v1/workspaces/{ws(world, 'a1')}/members", 200),
                         (f"/api/v1/workspaces/{ws(world, 'b1')}/recommendations", 404),
                         ("/api/v1/me", 200)):  # /me входит в каждый workspace в savepoint
        assert api.get(path, headers=cookie(token)).status_code == status, path
        assert pooled_workspace_setting(api.app_) == "", path
    viewer = session(rw, world["viewer"])
    assert api.get(f"/api/v1/workspaces/{ws(world, 'a1')}/members", headers=cookie(viewer)).status_code == 403
    assert pooled_workspace_setting(api.app_) == ""  # ошибка после входа в workspace — откат, контекста нет


def test_pool_discards_connection_with_leaked_session_context(api, world):
    """Кто-то выставил app.workspace_id на сессию в обход tenancy — пул не отдаст такое соединение следующему."""
    pool = api.app_.state.pool
    with pool.connection() as conn:
        conn.execute("SELECT set_config('app.workspace_id', %s, false)", (str(world["b1"]),))
    assert pooled_workspace_setting(api.app_) == ""


@pytest.mark.parametrize("role", ["postgres", "app_migrator", "app_system", "app_token"])
def test_api_refuses_role_other_than_app_rw(db, role):
    """Суперпользователь, владелец таблиц (вне RLS без FORCE), app_system (USING true) и app_token (токены любого
    workspace) отключили бы изоляцию — API с такой ролью не стартует."""
    app = create_app(settings(db, role, pool_timeout=1.0))
    with pytest.raises(PoolTimeout):
        with client_for(app):
            pass


def test_rls_is_the_second_barrier(db, world):
    """Даже без фильтра workspace_id в SQL прикладная роль API видит только рекомендации текущего workspace."""
    with db("app_rw") as conn:
        conn.autocommit = False
        enter_workspace(conn, world["owner"], world["a1"])
        assert {r[0] for r in conn.execute("SELECT id FROM recommendations")} == {world["rec_a1"]["rec"]}
        conn.rollback()
        assert conn.execute("SELECT current_setting('app.workspace_id', true)").fetchone()[0] in ("", None)
        conn.rollback()


# --- CSRF: изменяющие методы только с нашего Origin ---------------------------------------------------

@pytest.mark.parametrize("headers", [{"Origin": "https://evil.example"}, {}, {"Origin": "null"},
                                     {"Origin": ORIGIN + ".evil.example"}, {"Origin": "http://app.example.test"}])
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_foreign_origin_on_unsafe_method_is_csrf_rejected(api, rw, world, method, headers):
    token = session(rw, world["owner"])
    r = api.request(method, f"/api/v1/workspaces/{ws(world, 'a1')}/members", headers={**cookie(token), **headers})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_rejected"


def test_allowed_origin_passes_csrf(api, rw, world):
    token = session(rw, world["owner"])
    r = api.post(f"/api/v1/workspaces/{ws(world, 'a1')}/members", headers={**cookie(token), "Origin": ORIGIN})
    assert r.status_code == 405  # CSRF пройден; изменяющих эндпоинтов в этом срезе нет
