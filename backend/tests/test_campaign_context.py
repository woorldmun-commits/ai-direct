"""Контекст кампании из Campaigns.get: нормализация стратегии, fail-safe для неизвестных значений, матрица действий.

ВНИМАНИЕ: ответы API здесь собраны по документации (ref-v5/campaigns/get-*-campaign), не записаны с живого API.
Первый прогон на песочнице должен заменить их записанными обезличенными ответами (tests/fixtures/direct/)."""

import json
from decimal import Decimal

import httpx
import pytest

from app.sources.campaigns import STRATEGY_ACTIONS, Strategy, get_campaign_contexts, parse_campaign
from app.sources.direct import ConnectionUnavailable, DirectApiError, RetryLater


def campaign(ctype="UNIFIED_CAMPAIGN", search=None, network=None, cid=101, **extra):
    specific = {"BiddingStrategy": {"Search": search or {"BiddingStrategyType": "HIGHEST_POSITION"},
                                    "Network": network or {"BiddingStrategyType": "NETWORK_DEFAULT"}},
                "PriorityGoals": {"Items": [{"GoalId": 111, "Value": 1000000, "IsMetrikaSourceOfValue": "NO"}]},
                "CounterIds": {"Items": [555]}, **extra}
    key = {"UNIFIED_CAMPAIGN": "UnifiedCampaign", "TEXT_CAMPAIGN": "TextCampaign"}.get(ctype, "Other")
    return {"Id": cid, "Type": ctype, "Currency": "RUB", key: specific}


AVERAGE_CPA = {"BiddingStrategyType": "AVERAGE_CPA",
               "AverageCpa": {"AverageCpa": 5000000000, "GoalId": 111, "WeeklySpendLimit": None}}


def test_average_cpa_campaign():
    ctx = parse_campaign(campaign(search=AVERAGE_CPA))
    assert ctx.strategy is Strategy.AUTO_CPA
    assert (ctx.search.provider_type, ctx.search.target_cpa, ctx.search.goal_id) == ("AVERAGE_CPA", Decimal(5000), 111)
    assert (ctx.priority_goals, ctx.counter_ids, ctx.source) == ((111,), (555,), "campaigns.get@v5")


@pytest.mark.parametrize("search, network, expected", [
    ({"BiddingStrategyType": "HIGHEST_POSITION"}, None, Strategy.MANUAL_BIDDING),           # сети — как поиск
    ({"BiddingStrategyType": "SERVING_OFF"}, {"BiddingStrategyType": "MAXIMUM_COVERAGE"},
     Strategy.MANUAL_BIDDING),                                                              # только сети, вручную
    ({"BiddingStrategyType": "PAY_FOR_CONVERSION", "PayForConversion": {"Cpa": 3000000000, "GoalId": 111}}, None,
     Strategy.PAY_FOR_CONVERSION),
    ({"BiddingStrategyType": "WB_MAXIMUM_CONVERSION_RATE"}, None, Strategy.MAX_CONVERSIONS),
    ({"BiddingStrategyType": "AVERAGE_CRR"}, None, Strategy.UNSUPPORTED),                    # ДРР — не наш рычаг
    (AVERAGE_CPA, {"BiddingStrategyType": "WB_MAXIMUM_CLICKS"}, Strategy.UNSUPPORTED),        # смешанная
    ({"BiddingStrategyType": "SERVING_OFF"}, {"BiddingStrategyType": "SERVING_OFF"}, Strategy.SERVING_OFF),
])
def test_strategy_normalization(search, network, expected):
    assert parse_campaign(campaign(search=search, network=network)).strategy is expected


def test_new_api_value_is_unknown_not_a_crash():
    """API добавил стратегию, которой мы не знаем: исходное значение сохраняется, рычага нет — только наблюдение."""
    ctx = parse_campaign(campaign(search={"BiddingStrategyType": "AI_MAGIC_BIDDING"}))
    assert (ctx.search.provider_type, ctx.strategy) == ("AI_MAGIC_BIDDING", Strategy.UNKNOWN)
    assert STRATEGY_ACTIONS[ctx.strategy] == (None, "inspect_only")


def test_unsupported_campaign_type_reads_no_strategy():
    ctx = parse_campaign({"Id": 7, "Type": "CPM_BANNER_CAMPAIGN", "Currency": "RUB"})
    assert (ctx.search, ctx.strategy) == (None, Strategy.UNSUPPORTED)


def test_text_campaign_is_parsed_the_same_way():
    assert parse_campaign(campaign("TEXT_CAMPAIGN", search=AVERAGE_CPA)).strategy is Strategy.AUTO_CPA


def test_every_strategy_has_an_action_row_and_change_only_with_a_lever():
    """Матрица — продуктовый контракт: каждая стратегия в ней есть; change/review — только при наличии рычага."""
    assert set(STRATEGY_ACTIONS) == set(Strategy)
    for strategy, (action, level) in STRATEGY_ACTIONS.items():
        assert (action is None) == (level == "inspect_only"), strategy
    assert STRATEGY_ACTIONS[Strategy.MANUAL_BIDDING][0] == "change_bid"
    assert STRATEGY_ACTIONS[Strategy.AUTO_CPA][0] == "change_target_cpa"   # на автостратегии ставку не меняют
    assert STRATEGY_ACTIONS[Strategy.PAY_FOR_CONVERSION][1] == "review"


# --- HTTP: только чтение ------------------------------------------------------------------------------

def test_request_shape_and_agency_client_login():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"result": {"Campaigns": [campaign(search=AVERAGE_CPA)]}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    out = get_campaign_contexts(http, "tok", "client-a", [101], env="sandbox")
    req = seen[0]
    body = json.loads(req.content)
    assert str(req.url) == "https://api-sandbox.direct.yandex.com/json/v5/campaigns"
    assert (req.headers["Authorization"], req.headers["Client-Login"]) == ("Bearer tok", "client-a")
    assert body["method"] == "get" and body["params"]["SelectionCriteria"] == {"Ids": [101]}
    assert body["params"]["UnifiedCampaignFieldNames"] == ["BiddingStrategy", "PriorityGoals", "CounterIds"]
    assert out[101].strategy is Strategy.AUTO_CPA


def test_own_account_sends_no_client_login():
    seen = []
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: seen.append(r) or httpx.Response(200, json={"result": {}})))
    assert get_campaign_contexts(http, "tok", None, [1]) == {}
    assert "Client-Login" not in seen[0].headers


def error(code):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
        "error": {"error_code": code, "error_string": "…", "request_id": "8695244274068608439"}})))


def test_api_error_keeps_code_and_request_id():
    with pytest.raises(DirectApiError) as e:
        get_campaign_contexts(error(8000), "tok", None, [1])
    assert (e.value.error_code, e.value.request_id) == (8000, "8695244274068608439")


def test_auth_error_is_connection_error_like_in_reports():
    with pytest.raises(ConnectionUnavailable, match="token_expired"):
        get_campaign_contexts(error(53), "tok", None, [1])


def raw(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def down(request):
    raise httpx.ConnectError("boom")


@pytest.mark.parametrize("http", [raw(down), raw(lambda r: httpx.Response(502, text="<html>bad gateway</html>"))])
def test_network_or_gateway_failure_is_retried_like_in_reports(http):
    with pytest.raises(RetryLater):
        get_campaign_contexts(http, "tok", None, [1])


@pytest.mark.parametrize("response", [httpx.Response(200, text="not json"), httpx.Response(200, json={"result": 1})])
def test_malformed_success_is_api_error_not_crash(response):
    with pytest.raises(DirectApiError):
        get_campaign_contexts(raw(lambda r: response), "tok", None, [1])


def test_request_id_from_server_is_not_trusted_into_logs():
    http = raw(lambda r: httpx.Response(200, json={"error": {"error_code": 8000, "request_id": "1\nFAKE LOG LINE"}}))
    with pytest.raises(DirectApiError) as e:
        get_campaign_contexts(http, "tok", None, [1])
    assert e.value.request_id is None
