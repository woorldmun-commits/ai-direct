"""Smoke-тест scripts/e2e_account.py: весь путь MVP-0 на подставленном транспорте (ответы по документации).
Проверяет сборку цепочки и вывод, а не Яндекс: семантику подтвердит только реальный аккаунт."""

import json
import sys

import httpx

from scripts import e2e_account
from test_direct_sync import CID, TO, campaign_tsv, query_tsv
from test_metrika_sync import bytime, goals_json

CAMPAIGNS = {"result": {"Campaigns": [{"Id": CID, "Type": "UNIFIED_CAMPAIGN", "Currency": "RUB", "UnifiedCampaign": {
    "BiddingStrategy": {"Search": {"BiddingStrategyType": "AVERAGE_CPA",
                                   "AverageCpa": {"AverageCpa": 5000000000, "GoalId": 111}},
                        "Network": {"BiddingStrategyType": "NETWORK_DEFAULT"}}}}]}}


def yandex(request):
    path = request.url.path
    if path.endswith("/reports"):
        report = json.loads(request.content)["params"]["ReportType"]
        return httpx.Response(200, text=campaign_tsv() if report == "CAMPAIGN_PERFORMANCE_REPORT" else query_tsv())
    if path.endswith("/campaigns"):
        return httpx.Response(200, json=CAMPAIGNS)
    if path.endswith("/goals"):
        return httpx.Response(200, text=goals_json(111, 222))
    return httpx.Response(200, text=bytime())


def test_full_path_prints_finding_and_summary_row(monkeypatch, capsys):
    real = e2e_account.api_client
    monkeypatch.setattr(e2e_account, "api_client", lambda provider: real(provider, httpx.MockTransport(yandex)))
    monkeypatch.setenv("YANDEX_API_TOKEN", "y0_E2E_SECRET")
    monkeypatch.setattr(sys, "argv", ["e2e", "--login", "client-a", "--counter", "555", "--goals", "111,222",
                                      "--target-cpa", "3000", "--period-to", TO.isoformat()])
    e2e_account.main()
    out = capsys.readouterr().out
    assert "high_cpa_target@1 → review" in out and "стратегия auto_cpa (AVERAGE_CPA)" in out
    assert "проверьте перед изменением" in out
    assert "client-a | 1 | 38 | {'auto_cpa': 1} | 1 | 0 | 1 | 0 |" in out
    assert "y0_E2E_SECRET" not in out
