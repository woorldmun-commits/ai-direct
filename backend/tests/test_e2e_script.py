"""Smoke-тест scripts/e2e_account.py: весь путь MVP-0 на подставленном транспорте (ответы по документации).
Проверяет сборку цепочки, проверки целостности и артефакт прогона, а не Яндекс: семантику подтвердит только
реальный аккаунт."""

import json
import sys

import httpx
import pytest

from scripts import e2e_account
from test_direct_sync import CID, TO, campaign_tsv, query_tsv
from test_metrika_sync import bytime, goals_json


def campaigns(tz="Europe/Moscow"):
    return {"result": {"Campaigns": [{"Id": CID, "Type": "UNIFIED_CAMPAIGN", "Currency": "RUB", "TimeZone": tz,
                                      "UnifiedCampaign": {"BiddingStrategy": {
                                          "Search": {"BiddingStrategyType": "AVERAGE_CPA",
                                                     "AverageCpa": {"AverageCpa": 5000000000, "GoalId": 111}},
                                          "Network": {"BiddingStrategyType": "NETWORK_DEFAULT"}}}}]}}


def yandex(campaign_tz="Europe/Moscow", counter_tz="Europe/Moscow", report_error=None):
    def handler(request):
        path = request.url.path
        if path.endswith("/reports"):
            if report_error:
                return httpx.Response(400, json={"error": {"error_code": report_error, "request_id": "42"}})
            report = json.loads(request.content)["params"]["ReportType"]
            return httpx.Response(200, text=campaign_tsv() if report == "CAMPAIGN_PERFORMANCE_REPORT" else query_tsv())
        if path.endswith("/campaigns"):
            return httpx.Response(200, json=campaigns(campaign_tz))
        if path.endswith("/counters"):
            return httpx.Response(200, json={"counters": [{"id": 555, "name": "x", "time_zone_name": counter_tz}]})
        if path.endswith("/goals"):
            return httpx.Response(200, text=goals_json(111, 222))
        return httpx.Response(200, text=bytime())
    return handler


@pytest.fixture
def run(monkeypatch, capsys, tmp_path):
    def go(**kw):
        real = e2e_account.api_client
        monkeypatch.setattr(e2e_account, "api_client",
                            lambda provider: real(provider, httpx.MockTransport(yandex(**kw))))
        monkeypatch.setenv("YANDEX_API_TOKEN", "y0_E2E_SECRET")
        monkeypatch.setattr(sys, "argv", ["e2e", "--login", "client-a", "--counter", "555", "--goals", "111,222",
                                          "--target-cpa", "3000", "--period-to", TO.isoformat(),
                                          "--out", str(tmp_path)])
        e2e_account.main()
        [run_dir] = list(tmp_path.iterdir())
        return capsys.readouterr().out, json.loads((run_dir / "run.json").read_text(encoding="utf-8")), run_dir
    return go


def test_full_path_passes_and_leaves_artifact(run):
    out, r, run_dir = run()
    assert "high_cpa_target@1 → review" in out and "стратегия auto_cpa (AVERAGE_CPA)" in out
    assert r["status"] == "PASS" and "STATUS: PASS" in (run_dir / "summary.txt").read_text(encoding="utf-8")
    i = r["integrity"]
    assert (i["dates_expected"], i["dates_found"], i["duplicate_rows"]) == (37, 3, 0)
    assert len(i["no_row_observation_dates"]) == 34               # API не вернул строк: не доказанный ноль
    assert (i["spend"], i["clicks"], i["conversions"], i["computed_cpa"]) == ("157200.00", 1000, "38", "4136.84")
    assert i["sums_match"] and i["cpa_check"]
    assert [d["campaigns"] for d in i["by_date"]] == [1, 1, 1]
    assert r["metrika"]["report_rows"] == r["metrika"]["rows_expected"] == 74
    assert (r["audit"]["findings"], r["audit"]["review"], r["audit"]["change"]) == (1, 1, 0)
    assert r["strategies"] == {"auto_cpa": 1} and r["time_zones"]["match"]


def test_no_secrets_or_login_in_output_and_files(run):
    out, r, run_dir = run()
    files = "".join(f.read_text(encoding="utf-8") for f in run_dir.iterdir())
    for secret in ("y0_E2E_SECRET", "client-a"):
        assert secret not in files
    assert "y0_E2E_SECRET" not in out
    assert len(r["account"]) == 12                                  # логин — хэшем


@pytest.mark.parametrize("kw", [dict(campaign_tz="Asia/Yekaterinburg"), dict(counter_tz="Europe/Kaliningrad")])
def test_sources_in_different_time_zones_need_review(run, kw):
    _, r, _ = run(**kw)
    assert (r["status"], r["time_zones"]["match"]) == ("REVIEW", False)


def test_same_non_moscow_time_zone_in_both_sources_passes(run):
    """Екатеринбург и в Директе, и в Метрике — граница суток одна; отличие от пояса продукта видно отдельно."""
    _, r, _ = run(campaign_tz="Asia/Yekaterinburg", counter_tz="Asia/Yekaterinburg")
    assert (r["status"], r["time_zones"]["match"], r["time_zones"]["product_match"]) == ("PASS", True, False)


def test_rejected_report_is_fail_and_artifact_is_written(monkeypatch, tmp_path, capsys):
    real = e2e_account.api_client
    monkeypatch.setattr(e2e_account, "api_client",
                        lambda provider: real(provider, httpx.MockTransport(yandex(report_error=8000))))
    monkeypatch.setenv("YANDEX_API_TOKEN", "t")
    monkeypatch.setattr(sys, "argv", ["e2e", "--login", "c", "--counter", "555", "--goals", "111",
                                      "--period-to", TO.isoformat(), "--out", str(tmp_path)])
    with pytest.raises(SystemExit):
        e2e_account.main()
    [run_dir] = list(tmp_path.iterdir())
    r = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert r["status"] == "FAIL" and r["errors"]["direct"] == "invalid_request request_id=42"


@pytest.mark.parametrize("campaigns, found, insufficient, account_skipped, label", [
    ({1, 2}, {1}, set(), False, "FINDINGS"),
    ({1, 2}, set(), {2}, False, "NO_PROBLEMS_FOUND"),          # кампания 1 проверена — проблем нет
    ({1, 2}, set(), {1, 2}, False, "NO_ACTIONABLE_DATA"),      # проверить было не по чему
    ({1, 2}, set(), set(), True, "NO_ACTIONABLE_DATA"),        # правило не вычислялось: нет источника
    (set(), set(), set(), False, "NO_ACTIONABLE_DATA"),        # кампаний с показами нет
])
def test_zero_findings_is_not_one_outcome(campaigns, found, insufficient, account_skipped, label):
    assert e2e_account.outcome(campaigns, found, insufficient, account_skipped)["outcome"] == label


def test_outcome_in_artifact(run):
    _, r, _ = run()
    assert (r["audit"]["outcome"], r["audit"]["campaigns_with_findings"]) == ("FINDINGS", 1)
