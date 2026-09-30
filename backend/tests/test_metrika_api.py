"""Клиент Метрики (MetrikaApi) и онбординг целей. Сеть подменена httpx.MockTransport; формат ответов — по
документации management/openapi (counters, goals) и stat/v1. Заменить записанными ответами, когда будет токен."""

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.sources.metrika import MetrikaApi, MetrikaUnavailable
from app.sources.metrika_discovery import (MetrikaGoal, parse_counters, parse_goal_list, score_goal,
                                           suggest_goals)
from app.sync.snapshot import SyncFailure, sync_metrika
from test_direct_sync import FROM, GOALS, TO
from test_metrika_sync import SPEC, bytime, goals_json


def api(handler):
    return MetrikaApi(httpx.Client(transport=httpx.MockTransport(handler)), "y0_METRIKA")


def respond(status=200, body="{}"):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, text=body)
    return handler, seen


# --- HTTP -----------------------------------------------------------------------------------------------

def test_goals_request():
    handler, seen = respond(body=goals_json(111, 222))
    assert api(handler).fetch_goals(555) == goals_json(111, 222)
    assert str(seen[0].url) == "https://api-metrika.yandex.net/management/v1/counter/555/goals"
    assert seen[0].headers["Authorization"] == "OAuth y0_METRIKA"


def test_bytime_request_carries_the_whole_definition():
    """Цели и модель атрибуции — те же, что ушли в отчёт Директа (одно ConversionDefinition)."""
    handler, seen = respond(body=bytime())
    api(handler).fetch_bytime(SPEC)
    q = {k: v[0] for k, v in parse_qs(urlparse(str(seen[0].url)).query).items()}
    assert seen[0].url.path == "/stat/v1/data/bytime"
    assert q == {"ids": "555", "metrics": "ym:s:goal111reaches,ym:s:goal222reaches", "date1": FROM.isoformat(),
                 "date2": TO.isoformat(), "group": "day", "attribution": "cross_device_last_significant",
                 "accuracy": "full"}                                          # пустые dimensions не отправляются


@pytest.mark.parametrize("status, code", [(400, "invalid_request"), (401, "access_denied"), (403, "access_denied"),
                                          (404, "counter_not_found"), (429, "report_unavailable"),
                                          (500, "report_unavailable")])
def test_http_errors(status, code):
    handler, _ = respond(status, '{"errors": [{"message": "…"}]}')
    with pytest.raises(MetrikaUnavailable) as e:
        api(handler).fetch_goals(555)
    assert (e.value.counter_id, e.value.error_code) == (555, code)


def test_network_failure():
    def down(request):
        raise httpx.ConnectError("down")
    with pytest.raises(MetrikaUnavailable, match="report_unavailable"):
        api(down).fetch_bytime(SPEC)


def test_token_not_in_repr():
    assert "y0_METRIKA" not in repr(api(respond()[0]))


def test_sync_metrika_through_api():
    """Путь снимка целиком: список целей → проверка, что цели определения есть → отчёт → строки site_goal."""
    def handler(request):
        return httpx.Response(200, text=goals_json(111, 222) if request.url.path.endswith("/goals") else bytime())
    rows = sync_metrika(api(handler), GOALS, FROM, TO)
    assert len(rows) == 2 * 37 and {r.goal_id for r in rows} == {111, 222}


def test_sync_metrika_access_denied_is_failure_not_crash():
    handler, _ = respond(403)
    assert sync_metrika(api(handler), GOALS, FROM, TO) == SyncFailure("counter:555", "access_denied")


# --- Онбординг: счётчики и цели --------------------------------------------------------------------------

def test_counters_list():
    body = json.dumps({"rows": 2, "counters": [
        {"id": 555, "name": "Сайт", "site2": {"site": "shop.ru"}, "status": "Active", "permission": "own",
         "time_zone_name": "Europe/Moscow", "owner_login": "ivan", "code_status": "CS_OK"},
        {"id": 777, "name": "Лендинг", "status": "Active", "permission": "view"}]})
    handler, seen = respond(body=body)
    counters = parse_counters(api(handler).fetch_counters())
    assert [(c.id, c.site, c.permission) for c in counters] == [(555, "shop.ru", "own"), (777, None, "view")]
    assert parse_qs(urlparse(str(seen[0].url)).query) == {"per_page": ["1000"], "status": ["Active"]}


def goal(gid, name, gtype="action", source="user"):
    return MetrikaGoal(gid, name, gtype, source)


@pytest.mark.parametrize("g, level, reason", [
    (goal(1, "Отправка заявки"), "high", "purchase_or_lead"),
    (goal(2, "Оформление заказа", "url"), "high", "purchase_or_lead"),
    (goal(3, "Оплата", "payment_system"), "high", "purchase_or_lead"),
    (goal(4, "Клик по телефону", "phone"), "medium", "contact_click"),
    (goal(5, "Переход в WhatsApp", "messenger"), "medium", "contact_click"),
    (goal(6, "Просмотр 3 страниц", "number"), "low", "engagement_only"),
    (goal(7, "Время на сайте 60 с", "visit_duration"), "low", "engagement_only"),
    (goal(8, "Скачал прайс «заказать»", "file"), "low", "engagement_only"),  # слово не делает скачивание заявкой
    (goal(9, "Страница о компании", "url"), "low", "unclear"),
])
def test_goal_scoring(g, level, reason):
    c = score_goal(g)
    assert (c.level, c.reason) == (level, reason)


def test_suggestion_prefers_leads_then_contacts_never_engagement():
    leads = (goal(10, "Заявка"), goal(3, "Покупка", "payment_system"), goal(4, "Звонок", "phone"))
    assert [c.goal.id for c in suggest_goals(leads)] == [3, 10]                 # high есть — medium не предлагаем
    assert [c.goal.id for c in suggest_goals((goal(4, "Звонок", "phone"), goal(6, "Глубина", "number")))] == [4]
    assert suggest_goals((goal(6, "Глубина", "number"), goal(9, "О компании", "url"))) == ()  # честно: не нашли


def test_suggestion_respects_direct_goal_limit():
    many = tuple(goal(i, f"Заявка {i}") for i in range(1, 15))
    assert len(suggest_goals(many)) == 10


def test_goal_list_parsing():
    body = json.dumps({"goals": [{"id": 111, "name": "Заявка", "type": "action", "goal_source": "auto",
                                  "is_favorite": False, "default_price": 0, "conditions": []}]})
    assert parse_goal_list(body) == (MetrikaGoal(111, "Заявка", "action", "auto"),)
