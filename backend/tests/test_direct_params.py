"""Чтение параметров объекта для сверки (sources/direct_params.py): allowlist методов чтения, разбор ответов
Campaigns.get / KeywordBids.get, деньги из микро-единиц, ошибки → ParamsUnavailable.
Сеть подменена httpx.MockTransport; ответы — по документации Direct API v5 (ПРОВЕРИТЬ на песочнице)."""

import json
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

from app.sources.direct_params import (READ_METHODS, DirectReadClient, ObjectParams, ParamsFormatError,
                                       ParamsUnavailable, WriteMethodForbidden, money, needs_bids,
                                       parse_campaign_params, read_object_params, summarize_bids)

NOW = datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc)
DECREASE_BID = {"type": "decrease_bid", "change_pct": "-15.00", "execution": "manual"}
EXCLUDE = {"type": "exclude_placements", "placements_count": 1, "placements": [{"id": "1", "name": "a.ru"}],
           "execution": "manual"}


def campaign(cid=11, *, search=None, network=None, sites=("www.Games.example.com", "b.ru"), negatives=("бесплатно",),
             goals=((101, 500_000_000),), ctype="TEXT_CAMPAIGN", budget=1_500_000_000):
    """Campaigns.get → Campaigns[i] по документации: деньги в микро-единицах."""
    search = search or {"BiddingStrategyType": "AVERAGE_CPA",
                        "AverageCpa": {"AverageCpa": 850_000_000, "GoalId": 101, "WeeklySpendLimit": 30_000_000_000,
                                       "BidCeiling": None}}
    network = network or {"BiddingStrategyType": "NETWORK_DEFAULT", "NetworkDefault": {"LimitPercent": 100}}
    specific = {"BiddingStrategy": {"Search": search, "Network": network},
                "PriorityGoals": {"Items": [{"GoalId": g, "Value": v, "IsMetrikaSourceOfValue": "NO"}
                                            for g, v in goals]}}
    return {"Id": cid, "Type": ctype, "Currency": "RUB", "Status": "ACCEPTED", "State": "ON",
            "DailyBudget": {"Amount": budget, "Mode": "STANDARD"} if budget is not None else None,
            "ExcludedSites": {"Items": list(sites)} if sites is not None else None,
            "NegativeKeywords": {"Items": list(negatives)} if negatives is not None else None,
            {"TEXT_CAMPAIGN": "TextCampaign", "UNIFIED_CAMPAIGN": "UnifiedCampaign"}.get(ctype, "Other"): specific}


MANUAL = {"BiddingStrategyType": "HIGHEST_POSITION"}
SERVING_OFF = {"BiddingStrategyType": "SERVING_OFF"}


class FakeDirect:
    """Отвечает по пути: /v5/campaigns и /v5/keywordbids; записывает запросы."""

    def __init__(self, campaigns=None, bids_pages=(), status=200, error=None):
        self.campaigns = campaigns if campaigns is not None else [campaign()]
        self.bids_pages, self.status, self.error, self.requests = list(bids_pages), status, error, []

    def __call__(self, request):
        self.requests.append(request)
        if self.error:
            return httpx.Response(self.status, json={"error": {"error_code": self.error, "request_id": "77",
                                                               "error_string": "…"}})
        if request.url.path.endswith("/v5/campaigns"):
            return httpx.Response(200, json={"result": {"Campaigns": self.campaigns}})
        if request.url.path.endswith("/v5/keywordbids"):
            return httpx.Response(200, json={"result": self.bids_pages.pop(0)})
        return httpx.Response(404)

    def bodies(self):
        return [json.loads(r.content) for r in self.requests]


def client(fake, login="client-a"):
    return DirectReadClient(httpx.Client(transport=httpx.MockTransport(fake)), "y0_TOKEN", login)


# --- Allowlist методов --------------------------------------------------------------------------------------

def test_allowlist_is_read_only():
    assert READ_METHODS and all(method == "get" for _, method in READ_METHODS)


@pytest.mark.parametrize("service,method", [
    ("campaigns", "update"), ("campaigns", "add"), ("campaigns", "delete"), ("campaigns", "suspend"),
    ("campaigns", "resume"), ("campaigns", "archive"), ("campaigns", "unarchive"), ("keywordbids", "set"),
    ("keywordbids", "setAuto"), ("bids", "set"), ("ads", "moderate"), ("keywords", "update"),
    ("campaigns", "GET"), ("campaigns", "Get"), ("adgroups", "get"), ("reports", "get"),
])
def test_method_outside_allowlist_raises_before_network(service, method):
    fake = FakeDirect()
    with pytest.raises(WriteMethodForbidden):
        client(fake).call(service, method, {})
    assert fake.requests == []


def test_read_call_shape():
    fake = FakeDirect()
    client(fake).call("campaigns", "get", {"SelectionCriteria": {"Ids": [11]}, "FieldNames": ["Id"]})
    req = fake.requests[0]
    assert req.url == "https://api.direct.yandex.com/json/v5/campaigns"
    assert req.headers["Authorization"] == "Bearer y0_TOKEN" and req.headers["Client-Login"] == "client-a"
    assert fake.bodies()[0]["method"] == "get"


# --- Деньги ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (850_000_000, Decimal("850.00")), (1_234_567, Decimal("1.23")), (1_235_000, Decimal("1.24")),
    ("300000", Decimal("0.30")), (0, Decimal("0.00")), (None, None),
])
def test_money_from_micros(raw, expected):
    got = money(raw)
    assert got == expected and (got is None or got.as_tuple().exponent == -2)


@pytest.mark.parametrize("raw", [1.5, True, "abc", "1.5", -1, {"a": 1}])
def test_money_rejects_bad_values(raw):
    with pytest.raises(ParamsFormatError):
        money(raw)


# --- Разбор Campaigns.get -------------------------------------------------------------------------------------

def test_parse_auto_cpa_campaign():
    p = parse_campaign_params(campaign(), NOW)
    assert p.campaign_id == 11 and p.campaign_type == "TEXT_CAMPAIGN" and p.currency == "RUB"
    assert (p.status, p.state) == ("ACCEPTED", "ON")
    assert (p.daily_budget, p.daily_budget_mode) == (Decimal("1500.00"), "STANDARD")
    assert p.search.provider_type == "AVERAGE_CPA" and p.search.target_cpa == Decimal("850.00")
    assert p.search.goal_id == 101 and dict(p.search.money)["WeeklySpendLimit"] == Decimal("30000.00")
    assert "BidCeiling" not in dict(p.search.money)
    assert p.network.provider_type == "NETWORK_DEFAULT" and p.network.target_cpa is None
    assert p.priority_goals == ((101, Decimal("500.00")),)
    assert p.excluded_sites == ("b.ru", "games.example.com")  # нормализованы как имена площадок в выводах
    assert p.negative_keywords_count == 1 and "бесплатно" not in json.dumps(p.to_payload(), ensure_ascii=False)
    assert p.bids is None


def test_parse_pay_for_conversion_and_masked_site():
    p = parse_campaign_params(campaign(
        search={"BiddingStrategyType": "PAY_FOR_CONVERSION", "PayForConversion": {"Cpa": 700_000_000, "GoalId": 5}},
        sites=("ok.ru", "+7 999 123-45-67")))
    assert p.search.target_cpa == Decimal("700.00")
    assert p.excluded_sites == ("ok.ru",) and p.excluded_sites_masked == 1


def test_parse_missing_optional_blocks():
    p = parse_campaign_params(campaign(sites=None, negatives=None, goals=(), budget=None))
    assert p.excluded_sites == () and p.negative_keywords_count == 0 and p.priority_goals == ()
    assert p.daily_budget is None


@pytest.mark.parametrize("broken", [
    {"Id": 11},                                                                   # нет Type
    campaign(search={"AverageCpa": {}}),                                          # нет BiddingStrategyType
    campaign(search={"BiddingStrategyType": "AVERAGE_CPA", "AverageCpa": {"AverageCpa": 1.5}}),  # не микро-единицы
    {**campaign(), "ExcludedSites": {"Items": "a.ru"}},                           # Items не список
])
def test_parse_format_errors(broken):
    with pytest.raises(ParamsFormatError):
        parse_campaign_params(broken)


def test_hash_ignores_read_at_and_tracks_content():
    a = parse_campaign_params(campaign(), NOW)
    b = parse_campaign_params(campaign(), datetime(2026, 10, 5, tzinfo=timezone.utc))
    c = parse_campaign_params(campaign(sites=("b.ru",)), NOW)
    assert a.params_hash == b.params_hash != c.params_hash
    assert a == b  # read_at не участвует в сравнении


def test_payload_roundtrip():
    p = parse_campaign_params(campaign(), NOW)
    payload = json.loads(json.dumps(p.to_payload()))  # как в jsonb
    assert payload["search"]["money"][0] == ["AverageCpa", "850.00"]
    q = ObjectParams.from_payload(payload)
    assert q == p and q.params_hash == p.params_hash and q.read_at == NOW
    with pytest.raises(ValueError):
        ObjectParams.from_payload({**payload, "version": "object_params@0"})


# --- Ставки ---------------------------------------------------------------------------------------------------

def test_summarize_bids():
    s = summarize_bids([{"KeywordId": 2, "Search": {"Bid": 10_000_000}, "Network": {"Bid": 3_000_000}},
                        {"KeywordId": 1, "Search": {"Bid": 15_000_000}, "Network": {"Bid": 0}}])
    assert (s.count, s.search_mean, s.network_mean) == (2, Decimal("12.50"), Decimal("3.00"))
    same = summarize_bids([{"KeywordId": 1, "Search": {"Bid": 15_000_000}, "Network": {"Bid": 0}},
                           {"KeywordId": 2, "Search": {"Bid": 10_000_000}, "Network": {"Bid": 3_000_000}}])
    assert same.signature == s.signature  # порядок строк не важен


def test_needs_bids():
    assert needs_bids(DECREASE_BID)
    assert needs_bids({"type": "lower_cpa", "levers": [{"lever": "decrease_bid"}]})
    assert not needs_bids({"type": "lower_cpa", "levers": [{"lever": "lower_target_cpa"}]})
    assert not needs_bids(EXCLUDE)


def test_read_manual_campaign_reads_bids_with_paging():
    fake = FakeDirect([campaign(search=MANUAL, network=SERVING_OFF)], bids_pages=[
        {"KeywordBids": [{"KeywordId": 1, "Search": {"Bid": 20_000_000}}], "LimitedBy": 1},
        {"KeywordBids": [{"KeywordId": 2, "Search": {"Bid": 10_000_000}}]},
    ])
    p = read_object_params(client(fake), 11, DECREASE_BID, NOW)
    assert isinstance(p, ObjectParams) and p.bids.count == 2 and p.bids.search_mean == Decimal("15.00")
    bodies = fake.bodies()
    assert [b["params"]["Page"]["Offset"] for b in bodies[1:]] == [0, 1]
    assert bodies[1]["params"]["SelectionCriteria"] == {"CampaignIds": [11]}
    assert all(b["method"] == "get" for b in bodies)


def test_read_auto_campaign_skips_bids():
    fake = FakeDirect()
    p = read_object_params(client(fake), 11, DECREASE_BID, NOW)
    assert p.bids is None and len(fake.requests) == 1
    body = fake.bodies()[0]["params"]
    assert "ExcludedSites" in body["FieldNames"] and "PriorityGoals" in body["TextCampaignFieldNames"]


def test_read_too_many_keywords():
    page = {"KeywordBids": [{"KeywordId": 1, "Search": {"Bid": 1_000_000}}], "LimitedBy": 1}
    fake = FakeDirect([campaign(search=MANUAL)], bids_pages=[page] * 10)
    p = read_object_params(client(fake), 11, DECREASE_BID, NOW)
    assert p.bids is None and p.bids_note == "too_many_keywords"


# --- Ошибки → ParamsUnavailable -------------------------------------------------------------------------------

@pytest.mark.parametrize("status,code,reason", [
    (200, 54, "access_denied"), (200, 8800, "account_not_found"), (200, 3000, "api_restricted"),
    (200, 53, "token_expired"), (200, 513, "permission_missing"), (200, 52, "api_unavailable"),
    (500, 1000, "api_unavailable"), (400, 8000, "api_error"),
])
def test_errors_become_unavailable(status, code, reason):
    got = read_object_params(client(FakeDirect(status=status, error=code)), 11, EXCLUDE, NOW)
    assert isinstance(got, ParamsUnavailable) and got.reason == reason


def test_transport_error_is_unavailable():
    def boom(request):
        raise httpx.ConnectError("down")
    got = read_object_params(client(boom), 11, EXCLUDE, NOW)
    assert got == ParamsUnavailable("api_unavailable", retry_in=60)


def test_campaign_not_found_unsupported_and_format():
    assert read_object_params(client(FakeDirect([])), 11, EXCLUDE, NOW) == ParamsUnavailable("campaign_not_found")
    cpm = campaign(ctype="CPM_BANNER_CAMPAIGN")
    assert read_object_params(client(FakeDirect([cpm])), 11, EXCLUDE, NOW).reason == "unsupported_campaign_type"
    broken = {**campaign(), "DailyBudget": {"Amount": 1.5}}
    assert read_object_params(client(FakeDirect([broken])), 11, EXCLUDE, NOW).reason == "format_error"
    bad_bids = FakeDirect([campaign(search=MANUAL)], bids_pages=[{"KeywordBids": [{"Search": {"Bid": 1}}]}])
    assert read_object_params(client(bad_bids), 11, DECREASE_BID, NOW).reason == "format_error"


def test_unknown_reason_rejected():
    with pytest.raises(ValueError):
        ParamsUnavailable("whatever")
