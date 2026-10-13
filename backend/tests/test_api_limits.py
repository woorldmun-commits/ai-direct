"""Лимиты (решение владельца 2026-10-13): кабинетов в анализе по тарифу 1 / 5 / 25 (без подписки — как start),
не больше 10 рекомендаций на кабинет в начале списка; выбор счётчика и целей Метрики."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.api import create_app
from app.api.active import FINDINGS_PER_ACCOUNT, budgeted
from app.api.entitlements import MAX_AD_ACCOUNTS
from test_api_support import ORIGIN, client_for, cookie, session, settings, world, ws  # noqa: F401
from test_schema import connected, one

pytestmark = pytest.mark.usefixtures("db")
NOW = datetime.now(timezone.utc)


@pytest.fixture
def c(db):
    with client_for(create_app(settings(db))) as client:
        yield client


def auth(rw, user: int) -> dict:
    return {**cookie(session(rw, user)), "Origin": ORIGIN}


# --- кабинеты по тарифу ------------------------------------------------------------------------------

def test_plan_limits_are_the_owner_decision():
    assert MAX_AD_ACCOUNTS == {"start": 1, "business": 5, "business_plus": 25}


def extra_account(rw, workspace: int) -> int:
    conn_id = one(rw, """SELECT da.direct_connection_id FROM direct_accounts da
                         JOIN direct_connections dc ON dc.id = da.direct_connection_id
                         WHERE dc.workspace_id = %s LIMIT 1""", workspace)
    return one(rw, "INSERT INTO direct_accounts (direct_connection_id, client_login) VALUES (%s, %s) RETURNING id",
               conn_id, f"extra-{workspace}-{datetime.now().timestamp()}")


def select(c, rw, world, account: int, selected: bool = True, who: str = "owner"):
    return c.patch(f"/api/v1/workspaces/{ws(world, 'a1')}/integrations/ad-accounts/acc_{account}",
                   json={"selected": selected}, headers=auth(rw, world[who]))


def subscribe(rw, workspace: int, plan: str, status: str = "active"):
    rw.execute("""INSERT INTO subscriptions (workspace_id, plan, status, price, current_period_start, current_period_end)
                  VALUES (%s, %s, %s, 4990, %s, %s)""", (workspace, plan, status, NOW - timedelta(1), NOW + timedelta(29)))


def test_without_subscription_second_account_is_over_limit(c, rw, world):
    r = select(c, rw, world, extra_account(rw, world["a1"]))  # первый кабинет a1 уже выбран
    assert r.status_code == 422 and r.json()["error"]["code"] == "action_unavailable"
    assert r.json()["error"]["reason"] == "entitlement_exceeded"


def test_business_plan_allows_more_and_deselect_is_always_allowed(c, rw, world):
    subscribe(rw, world["a1"], "business")
    extra = extra_account(rw, world["a1"])
    assert select(c, rw, world, extra).status_code == 200
    assert select(c, rw, world, extra, selected=False).status_code == 200


def test_expired_subscription_falls_back_to_start(c, rw, world):
    subscribe(rw, world["a1"], "business_plus", status="expired")
    assert select(c, rw, world, extra_account(rw, world["a1"])).status_code == 422


def test_reselecting_an_already_selected_account_is_not_counted_twice(c, rw, world):
    first = one(rw, """SELECT da.id FROM direct_accounts da JOIN direct_connections dc ON dc.id = da.direct_connection_id
                       WHERE dc.workspace_id = %s AND da.is_selected""", world["a1"])
    assert select(c, rw, world, first).status_code == 200


# --- не больше 10 рекомендаций на кабинет в начале списка ------------------------------------------------

@dataclass(frozen=True)
class FakeCard:
    rec_id: int
    account_id: int
    exposure: int


def test_budget_keeps_top_per_account_and_moves_the_rest_back():
    noisy = [FakeCard(i, 1, 1000 - i) for i in range(FINDINGS_PER_ACCOUNT + 3)]
    quiet = [FakeCard(100, 2, 5)]
    key = lambda card: -card.exposure  # noqa: E731
    shown, rest = budgeted(noisy + quiet, key)
    assert FINDINGS_PER_ACCOUNT == 10
    assert [card.rec_id for card in rest] == [10, 11, 12]          # хвост шумного кабинета, не потерян
    assert quiet[0] in shown and len(shown) == FINDINGS_PER_ACCOUNT + 1


def test_lists_report_how_many_are_beyond_the_budget(c, rw, world):
    h = auth(rw, world["owner"])
    assert c.get(f"/api/v1/workspaces/{ws(world, 'a1')}/recommendations", headers=h).json()["beyond_budget"] == 0
    counts = c.get(f"/api/v1/workspaces/{ws(world, 'a1')}/today", headers=h).json()["counts"]
    assert counts == {"active": 1, "beyond_budget": 0}


# --- счётчик и цели Метрики ------------------------------------------------------------------------------

@pytest.fixture
def counters(rw, world):
    conn_id = connected(rw, "metrika", world["a1"], f"metrika-{world['a1']}")
    ids = [one(rw, "INSERT INTO metrika_counters (metrika_connection_id, counter_id) VALUES (%s, %s) RETURNING id",
               conn_id, counter) for counter in (111, 222)]
    return ids


def goals_url(world) -> str:
    return f"/api/v1/workspaces/{ws(world, 'a1')}/integrations/yandex_metrika/goals"


def test_select_counter_and_goals(c, rw, world, counters):
    h = auth(rw, world["owner"])
    r = c.put(goals_url(world), json={"counter_id": "111", "goal_ids": ["7", "8"]}, headers=h)
    assert r.status_code == 200
    items = {i["counter_id"]: i for i in c.get(goals_url(world), headers=h).json()["items"]}
    assert items["111"] == {"counter_id": "111", "selected": True, "goal_ids": ["7", "8"]}
    assert items["222"]["selected"] is False
    c.put(goals_url(world), json={"counter_id": "222", "goal_ids": ["9"]}, headers=h)  # один выбранный на подключение
    items = {i["counter_id"]: i for i in c.get(goals_url(world), headers=h).json()["items"]}
    assert (items["111"]["selected"], items["222"]["selected"]) == (False, True)


def test_empty_goals_deselect_counter(c, rw, world, counters):
    h = auth(rw, world["owner"])
    c.put(goals_url(world), json={"counter_id": "111", "goal_ids": ["7"]}, headers=h)
    assert c.put(goals_url(world), json={"counter_id": "111", "goal_ids": []}, headers=h).status_code == 200
    items = {i["counter_id"]: i for i in c.get(goals_url(world), headers=h).json()["items"]}
    assert items["111"] == {"counter_id": "111", "selected": False, "goal_ids": []}


@pytest.mark.parametrize("body", [{"counter_id": "111", "goal_ids": ["7", "7"]},
                                  {"counter_id": "111", "goal_ids": [str(i) for i in range(1, 12)]},
                                  {"counter_id": "111", "goal_ids": ["abc"]},
                                  {"counter_id": "111", "goal_ids": ["0"]},
                                  {"counter_id": "111", "goal_ids": [7]},
                                  {"counter_id": "111", "goal_ids": ["7"], "evil": 1}])
def test_bad_goal_ids_are_400(c, rw, world, counters, body):
    assert c.put(goals_url(world), json=body, headers=auth(rw, world["owner"])).status_code == 400  # формат — 400


def test_unknown_counter_404_and_viewer_403(c, rw, world, counters):
    body = {"counter_id": "333", "goal_ids": ["7"]}
    assert c.put(goals_url(world), json=body, headers=auth(rw, world["owner"])).status_code == 404
    assert c.put(goals_url(world), json={**body, "counter_id": "111"},
                 headers=auth(rw, world["viewer"])).status_code == 403


def test_counter_of_another_workspace_is_404(c, rw, world, counters):
    foreign = connected(rw, "metrika", world["b1"], f"metrika-b-{world['b1']}")
    one(rw, "INSERT INTO metrika_counters (metrika_connection_id, counter_id) VALUES (%s, 444) RETURNING id", foreign)
    r = c.put(goals_url(world), json={"counter_id": "444", "goal_ids": ["7"]}, headers=auth(rw, world["owner"]))
    assert r.status_code == 404
    assert Decimal(one(rw, "SELECT count(*) FROM metrika_counters WHERE counter_id = 444 AND is_selected")) == 0
