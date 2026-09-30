"""Reports API Директа (DirectApi): форма запроса, 200/201/202, коды ошибок → классы источника, стабильный ReportName.
Сеть подменена httpx.MockTransport; ответы — по документации (reports/spec, headers, concepts/errors-list).
Заменить записанными ответами песочницы, когда будет доступ (tests/fixtures/direct/reports/)."""

import json
from datetime import date, timedelta

import httpx
import pytest

from app.sources.direct import (AccountUnavailable, ConnectionUnavailable, DirectApi, DirectApiError, RetryLater,
                                CAMPAIGN_REPORT)
from app.sync.snapshot import Snapshot, SyncFailure, sync_account
from test_direct_sync import GOALS, TO, campaign_tsv, query_tsv, root  # noqa: F401 — root: фикстура
from test_metrika_sync import metrika  # noqa: F401 — фикстура
from test_schema import chain, one  # noqa: F401 — фикстура
from test_worker_sync import new_run, work, ws  # noqa: F401 — фикстура
from app.worker.sync import Done, RetryAt

FROM = TO - timedelta(36)


class FakeReports:
    """responses: очередь (status, body, headers) для /reports; Campaigns.get отвечает campaigns_status/body."""

    def __init__(self, *responses, campaigns=(200, {"result": {"Campaigns": [{"Id": 1}]}})):
        self.responses, self.campaigns, self.requests = list(responses), campaigns, []

    def __call__(self, request):
        self.requests.append(request)
        if request.url.path.endswith("/campaigns"):
            return httpx.Response(self.campaigns[0], json=self.campaigns[1])
        status, body, headers = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(body, dict):
            return httpx.Response(status, json=body, headers=headers)
        return httpx.Response(status, text=body, headers=headers)

    def bodies(self):
        return [json.loads(r.content) for r in self.requests if r.url.path.endswith("/reports")]


def api(fake, run_key="42", env="api"):
    return DirectApi(httpx.Client(transport=httpx.MockTransport(fake)), "y0_TOKEN", run_key, env)


def ready(text):
    return (200, text, {"RequestId": "111"})


def error(status, code):
    return (status, {"error": {"request_id": "8695244274068608439", "error_code": code,
                               "error_string": "…", "error_detail": "…"}}, {"RequestId": "8695244274068608439"})


# --- Форма запроса --------------------------------------------------------------------------------------

def test_request_shape():
    fake = FakeReports(ready(campaign_tsv()))
    api(fake).fetch_report("client-a", CAMPAIGN_REPORT, GOALS, FROM, TO)
    req, body = fake.requests[0], fake.bodies()[0]["params"]
    assert str(req.url) == "https://api.direct.yandex.com/json/v501/reports"
    assert {k: req.headers[k] for k in ("Authorization", "Client-Login", "processingMode", "returnMoneyInMicros",
                                         "skipReportHeader", "skipReportSummary")} == {
        "Authorization": "Bearer y0_TOKEN", "Client-Login": "client-a", "processingMode": "auto",
        "returnMoneyInMicros": "false", "skipReportHeader": "true", "skipReportSummary": "true"}
    assert "skipColumnHeader" not in req.headers                 # по строке столбцов парсер сверяет ответ
    assert body == {
        "SelectionCriteria": {"DateFrom": FROM.isoformat(), "DateTo": TO.isoformat()},
        "FieldNames": ["Date", "CampaignId", "Impressions", "Clicks", "Cost", "Conversions"],  # Conversions — последним
        "ReportName": "ai-direct:42:CAMPAIGN_PERFORMANCE_REPORT", "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
        "DateRangeType": "CUSTOM_DATE", "Format": "TSV", "IncludeVAT": "YES",
        "Goals": ["111", "222"], "AttributionModels": ["LSCCD"],  # из ConversionDefinition, не из клиента API
    }


def test_without_goals_no_conversions_requested():
    fake = FakeReports(ready("x"))
    api(fake).fetch_report("client-a", CAMPAIGN_REPORT, None, FROM, TO)
    body = fake.bodies()[0]["params"]
    assert "Goals" not in body and "AttributionModels" not in body and "Conversions" not in body["FieldNames"]


def test_sandbox_endpoint():
    fake = FakeReports(ready("x"))
    api(fake, env="sandbox").fetch_report("c", CAMPAIGN_REPORT, None, FROM, TO)
    assert str(fake.requests[0].url) == "https://api-sandbox.direct.yandex.com/json/v501/reports"


@pytest.mark.parametrize("date_from, date_to, expected", [
    (date(2026, 9, 30), date(2026, 9, 30), ("2026-09-30", "2026-09-30")),     # один день
    (date(2026, 8, 25), date(2026, 9, 30), ("2026-08-25", "2026-09-30")),     # граница месяца
    (date(2026, 12, 1), date(2027, 1, 6), ("2026-12-01", "2027-01-06")),      # граница года, 37 дней
    (date(2028, 1, 24), date(2028, 2, 29), ("2028-01-24", "2028-02-29")),     # високосный февраль
])
def test_custom_dates(date_from, date_to, expected):
    fake = FakeReports(ready("x"))
    api(fake).fetch_report("c", CAMPAIGN_REPORT, None, date_from, date_to)
    crit = fake.bodies()[0]["params"]["SelectionCriteria"]
    assert (crit["DateFrom"], crit["DateTo"]) == expected


def test_reversed_period_is_rejected_before_calling_api():
    fake = FakeReports(ready("x"))
    with pytest.raises(ValueError):
        api(fake).fetch_report("c", CAMPAIGN_REPORT, None, TO, TO - timedelta(1))
    assert fake.requests == []


# --- 200 / 201 / 202 ------------------------------------------------------------------------------------

@pytest.mark.parametrize("status", [201, 202])
def test_report_not_ready_retries_in_server_interval(status):
    with pytest.raises(RetryLater) as e:
        api(FakeReports((status, "", {"retryIn": "17"}))).fetch_report("c", CAMPAIGN_REPORT, GOALS, FROM, TO)
    assert (e.value.retry_in, e.value.reason) == (17, "report_not_ready")


def test_retry_repeats_same_report_name_and_params():
    """Офлайн-режим: повтор — с тем же ReportName и теми же параметрами (иначе API ответит ошибкой)."""
    fake = FakeReports((201, "", {"retryIn": "5"}), (202, "", {"retryIn": "5"}), ready(campaign_tsv()))
    for _ in range(2):
        with pytest.raises(RetryLater):
            api(fake).fetch_report("c", CAMPAIGN_REPORT, GOALS, FROM, TO)
    api(fake).fetch_report("c", CAMPAIGN_REPORT, GOALS, FROM, TO)
    bodies = fake.bodies()
    assert len(bodies) == 3 and bodies[0] == bodies[1] == bodies[2]


def test_new_sync_run_gets_new_report_name():
    """Досинхронизация того же дня — новый sync_run: из офлайн-очереди не придёт отчёт утренней синхронизации."""
    fake = FakeReports(ready("x"))
    api(fake, run_key="42").fetch_report("c", CAMPAIGN_REPORT, GOALS, FROM, TO)
    api(fake, run_key="43").fetch_report("c", CAMPAIGN_REPORT, GOALS, FROM, TO)
    assert [b["params"]["ReportName"] for b in fake.bodies()] == [
        "ai-direct:42:CAMPAIGN_PERFORMANCE_REPORT", "ai-direct:43:CAMPAIGN_PERFORMANCE_REPORT"]


# --- Ошибки → классы источника --------------------------------------------------------------------------

@pytest.mark.parametrize("response, raised, code", [
    (error(400, 53), ConnectionUnavailable, "token_expired"),
    (error(400, 513), ConnectionUnavailable, "permission_missing"),
    (error(400, 54), AccountUnavailable, "access_denied"),
    (error(400, 8800), AccountUnavailable, "account_not_found"),
    (error(400, 3000), AccountUnavailable, "api_restricted"),
])
def test_access_errors(response, raised, code):
    with pytest.raises(raised) as e:
        api(FakeReports(response)).fetch_report("client-a", CAMPAIGN_REPORT, GOALS, FROM, TO)
    assert e.value.error_code == code


@pytest.mark.parametrize("response", [error(400, 152), error(500, 1000), error(400, 506), error(400, 52),
                                      (500, "<html>oops</html>", {}), (502, "", {"retryIn": "30"})])
def test_temporary_errors_are_retried(response):
    with pytest.raises(RetryLater) as e:
        api(FakeReports(response)).fetch_report("c", CAMPAIGN_REPORT, GOALS, FROM, TO)
    assert e.value.reason == "api_unavailable"


def test_network_failure_is_retried():
    def down(request):
        raise httpx.ConnectError("down")
    with pytest.raises(RetryLater):
        DirectApi(httpx.Client(transport=httpx.MockTransport(down)), "t", "1").fetch_report(
            "c", CAMPAIGN_REPORT, None, FROM, TO)


def test_invalid_request_keeps_request_id():
    with pytest.raises(DirectApiError) as e:
        api(FakeReports(error(400, 8000))).fetch_report("c", CAMPAIGN_REPORT, GOALS, FROM, TO)
    assert (e.value.error_code, e.value.request_id) == (8000, "8695244274068608439")


def test_token_not_in_repr():
    assert "y0_TOKEN" not in repr(api(FakeReports(ready("x"))))


def test_check_access_uses_campaigns_get():
    fake = FakeReports(ready("x"))
    api(fake).check_access("client-a")
    assert fake.requests[0].url.path == "/json/v5/campaigns"
    with pytest.raises(AccountUnavailable):
        api(FakeReports(ready("x"), campaigns=(200, error(200, 54)[1]))).check_access("client-a")


# --- Сквозной путь: API → парсер → снимок ---------------------------------------------------------------

def reports_by_type(request):
    body = json.loads(request.content)["params"]
    text = campaign_tsv() if body["ReportType"] == "CAMPAIGN_PERFORMANCE_REPORT" else query_tsv()
    return httpx.Response(200, text=text)


def test_sync_account_through_api():
    source = DirectApi(httpx.Client(transport=httpx.MockTransport(reports_by_type)), "t", "7")
    snap = sync_account(source, "client-a", GOALS, TO)
    assert isinstance(snap, Snapshot) and snap.rows and snap.conversion_definition == GOALS


def test_rejected_request_becomes_failure_with_request_id():
    out = sync_account(api(FakeReports(error(400, 8000))), "client-a", GOALS, TO)
    assert out == SyncFailure("client-a", "invalid_request", request_id="8695244274068608439")


def test_worker_waits_for_offline_report_then_writes_snapshot(rw, ws):
    """201 → запуск ждёт (RetryAt по retryIn) → повтор того же sync_run с тем же ReportName → 200 → снимок.
    Счётчик выбран (цели 111, 222 — как в отчёте), сама Метрика не запрашивается."""
    run_id = new_run(rw, ws)
    calls = []

    def handler(request):
        calls.append(json.loads(request.content)["params"]["ReportName"])
        if len(calls) == 1:
            return httpx.Response(201, headers={"retryIn": "10"})
        return reports_by_type(request)

    direct = DirectApi(httpx.Client(transport=httpx.MockTransport(handler)), "t", str(run_id))
    assert work(rw, ws, run_id, direct=direct, metrika_source=None) == RetryAt(10, "report_not_ready")
    assert isinstance(work(rw, ws, run_id, direct=direct, metrika_source=None), Done)
    assert calls[0] == calls[1] == f"ai-direct:{run_id}:CAMPAIGN_PERFORMANCE_REPORT"


def test_worker_records_request_id_of_rejected_request(rw, ws):
    run_id = new_run(rw, ws, with_metrika=False)
    work(rw, ws, run_id, direct=api(FakeReports(error(400, 8000)), run_key=str(run_id)), metrika_source=None)
    assert rw.execute("SELECT status, error_code, provider_request_id FROM sync_runs WHERE id = %s",
                      (run_id,)).fetchone() == ("failed", "invalid_request", "8695244274068608439")


# --- Безопасный лог HTTP -----------------------------------------------------------------------------------

def test_http_log_has_request_id_and_never_token_or_body(caplog):
    from app.sources.http import api_client

    def handler(request):
        return httpx.Response(400, json={"error": {"error_code": 8000, "request_id": "777"}},
                              headers={"RequestId": "777"})

    http = api_client("yandex_direct", httpx.MockTransport(handler))
    with caplog.at_level("DEBUG"):
        with pytest.raises(DirectApiError):
            DirectApi(http, "y0_SECRET_TOKEN", "9").fetch_report("client-a", CAMPAIGN_REPORT, GOALS, FROM, TO)
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "yandex_direct POST /json/v501/reports status=400 request_id=777" in text
    for secret in ("y0_SECRET_TOKEN", "Authorization", "Bearer", "client-a", "ReportName", "Goals"):
        assert secret not in text
