"""Chief routing fixtures: fabricated aggregates, never a customer report."""
from datetime import date
from decimal import Decimal

import pytest

from app.intelligence.agent_control import INDEX, SPECIALISTS
from app.intelligence.specialist_runtime import ADDITIONAL_AGENTS, chief_analyze
from test_intelligence_economics import calculate


def result(**options):
    values = {"cost": "14000", "clicks": 500, "impressions": 5000,
              "conversions": "40"}
    values.update(options.pop("values", {}))
    return calculate(values, start=date(2026, 10, 21), **options)


def days(spends=None):
    spends = spends or [100, 100, 100, 100, 100, 100, 100]
    return tuple({
        "date": date(2026, 10, 21 + index).isoformat(),
        "metrics": {"cost": {"amount": str(spend), "data_status": "complete"}},
    } for index, spend in enumerate(spends))


def by_role(report):
    return {item["role"]: item for item in report["specialists"]}


def test_all_eight_are_registered_and_on_demand_reports_are_complete():
    assert len(SPECIALISTS) == 20
    assert len(INDEX) == 21
    report = chief_analyze(result(), daily=days(),
                           profile={"revision": 1, "fields": {"industry_code": "b2b"}})
    assert report["chief"] == "chief_analyst"
    assert report["status"] == "review_required"
    assert set(by_role(report)) == set(ADDITIONAL_AGENTS)
    assert len(report["specialists"]) == 8
    assert report["external_llm"] is False
    assert report["publication_allowed"] is False
    assert report["advertising_write_allowed"] is False
    assert report["independent_review_verified"] is False
    assert by_role(report)["tracking_integrity"]["status"] == "review_required"
    assert by_role(report)["knowledge_steward"]["observations"]["knowledge_version"].startswith("starter-")
    for name in ("search_intent", "landing_cro", "customer_value"):
        assert by_role(report)[name]["status"] == "unavailable"
        assert by_role(report)[name]["observations"] == {}


def test_lead_quality_only_reports_a_sourced_fraction_not_a_sale():
    out = chief_analyze(result(values={"leads": 20, "qualified_leads": 5}))
    report = by_role(out)["lead_quality"]
    assert report["status"] == "review_required"
    assert report["observations"]["qualified_lead_share_pct"] == "25.00"
    assert len(report["evidence_ids"]) == 2
    assert "quality_rate_is_not_sale_rate" in report["reason_codes"]


@pytest.mark.parametrize("extra", [
    {"leads": 3, "qualified_leads": 4},
    {"leads": 0, "qualified_leads": 0},
])
def test_invalid_lead_counts_never_produce_a_quality_rate(extra):
    report = by_role(chief_analyze(result(values=extra)))["lead_quality"]
    assert report["status"] == "blocked"
    assert not report["observations"]


def test_missing_source_does_not_turn_into_zero():
    out = by_role(chief_analyze(result()))
    assert out["lead_quality"]["status"] == "unavailable"
    assert out["anomaly_sentinel"]["status"] == "unavailable"
    assert "six_complete_days_required" in out["anomaly_sentinel"]["reason_codes"]


def test_anomaly_candidate_only_with_six_complete_contiguous_days():
    out = by_role(chief_analyze(result(), daily=days([100, 100, 100, 400, 400, 400, 400])))
    found = out["anomaly_sentinel"]
    assert found["status"] == "review_required"
    assert found["observations"]["large_spend_change_candidate"] is True
    assert "candidate_only_not_statistical_anomaly" in found["reason_codes"]
    assert "causal_effect_not_established" in out["recommendation_challenger"]["reason_codes"]


def test_anomaly_does_not_depend_on_source_row_order():
    entries = days([100, 100, 100, 400, 400, 400, 400])
    one = by_role(chief_analyze(result(), daily=entries))["anomaly_sentinel"]
    other = by_role(chief_analyze(result(), daily=tuple(reversed(entries))))["anomaly_sentinel"]
    assert one == other


def test_anomaly_requires_complete_daily_rows_and_no_gaps():
    incomplete = list(days())
    incomplete[2]["metrics"]["cost"]["amount"] = None
    out = by_role(chief_analyze(result(), daily=tuple(incomplete)))
    assert out["anomaly_sentinel"]["status"] == "unavailable"
    gap = list(days())
    gap[2]["date"] = "2026-10-19"
    out = by_role(chief_analyze(result(), daily=tuple(gap)))
    assert out["anomaly_sentinel"]["status"] == "blocked"


def test_partial_or_stale_source_is_never_treated_as_complete():
    out = chief_analyze(result(quality_status="partial"), daily=days(),
                        profile={"fields": {"industry_code": "b2b"}})
    assert out["status"] == "blocked"
    assert by_role(out)["tracking_integrity"]["status"] == "blocked"
    assert by_role(out)["lead_quality"]["status"] == "blocked"


def test_unknown_quality_fails_closed():
    out = chief_analyze(result(quality_status="unknown"))
    assert out["status"] == "blocked"
    assert out["specialists"] == []
    assert out["publication_allowed"] is False


def test_unknown_industry_does_not_invent_benchmarks():
    out = by_role(chief_analyze(result(), profile={"fields": {"industry_code": "unknown-specialist"}}))
    industry = out["knowledge_steward"]
    assert industry["status"] == "review_required"
    assert industry["observations"] == {}
    assert "unclassified_industry_universal_fallback" in industry["reason_codes"]


def test_no_client_query_text_or_campaign_names_are_emitted():
    data = result()
    report = chief_analyze(data)
    assert all("search_term" not in str(item) for item in report["specialists"])
    assert report["source_refs"] == ["source:1"]


def test_no_open_access_to_external_execution_or_model():
    report = chief_analyze(result())
    for item in report["specialists"]:
        assert item["external_llm"] is False
        assert item["advertising_write_allowed"] is False
    assert by_role(report)["recommendation_challenger"]["status"] == "blocked"
