"""Safe on-demand Chief Analyst: deterministic routing over trusted scoped aggregates.

This is NOT autonomous LLM processing. It performs no writes, network requests,
query-string processing, or causality attribution. The caller MUST build the
AnalysisResult from its authenticated workspace snapshot; client-supplied JSON
is not trusted evidence. Its results never authorize a recommendation or ad edit.
"""
from datetime import date
from decimal import Decimal
from statistics import median

from app.intelligence.agent_control import INDEX
from app.intelligence.contracts import AnalysisResult, decimal_number
from app.intelligence.knowledge import industries

ADDITIONAL_AGENTS = (
    "lead_quality", "tracking_integrity", "search_intent", "landing_cro",
    "anomaly_sentinel", "customer_value", "knowledge_steward",
    "recommendation_challenger",
)
MAX_DAILY = 37


def _report(role: str, status: str, *, evidence: tuple[str, ...] = (),
            reasons: tuple[str, ...] = (), observations: dict | None = None) -> dict:
    if role not in INDEX:
        raise ValueError("unknown_agent")
    return {
        "role": role, "status": status, "evidence_ids": list(evidence),
        "reason_codes": list(reasons), "observations": observations or {},
        "external_llm": False, "advertising_write_allowed": False,
    }


def _metric(result: AnalysisResult, key: str):
    return result.metrics.get(key)


def _proof(result: AnalysisResult, *keys: str) -> tuple[str, ...]:
    evidence = {item.claim_id: item.id for item in result.evidence}
    return tuple(evidence[key] for key in keys if key in evidence)


def _safe_values(result: AnalysisResult, keys: tuple[str, ...]) -> bool:
    return all(
        (metric := _metric(result, key)) is not None
        and metric.value is not None and metric.status != "unavailable"
        for key in keys
    )


def _lead_quality(result: AnalysisResult) -> dict:
    role = "lead_quality"
    if result.context.quality_status != "complete":
        return _report(role, "blocked", reasons=("source_quality_not_complete",))
    keys = ("leads", "qualified_leads")
    if not _safe_values(result, keys):
        return _report(role, "unavailable", reasons=("qualified_lead_feed_required",))
    leads, qualified = (result.metrics[key].value for key in keys)
    if leads <= 0 or qualified < 0 or qualified > leads:
        return _report(role, "blocked", reasons=("lead_counts_inconsistent",))
    rate = qualified / leads * Decimal(100)
    return _report(role, "review_required", evidence=_proof(result, *keys),
                   reasons=("quality_rate_is_not_sale_rate",),
                   observations={"qualified_lead_share_pct": format(rate.quantize(Decimal("0.01")), "f")})


def _tracking_integrity(result: AnalysisResult) -> dict:
    role = "tracking_integrity"
    definition = result.context.conversion_definition
    if result.context.quality_status != "complete":
        return _report(role, "blocked", reasons=("source_quality_not_complete",))
    if not definition:
        return _report(role, "blocked", reasons=("conversion_definition_missing",))
    if not _safe_values(result, ("conversions", "clicks")):
        return _report(role, "unavailable", reasons=("conversion_or_clicks_missing",))
    return _report(role, "review_required",
                   evidence=_proof(result, "conversions", "clicks"),
                   reasons=("tracking_configuration_not_independently_audited",))


def _anomaly_sentinel(result: AnalysisResult, daily: tuple[dict, ...]) -> dict:
    role = "anomaly_sentinel"
    if result.context.quality_status != "complete":
        return _report(role, "blocked", reasons=("incomplete_or_stale_period",))
    if len(daily) > MAX_DAILY:
        return _report(role, "blocked", reasons=("daily_limit_exceeded",))
    # Only consume the four allowlisted aggregate fields from the server. If a
    # day is missing or partial, do NOT replace it by zero or interpolate it.
    entries: list[tuple[date, Decimal]] = []
    dates: set[date] = set()
    for row in daily:
        day = date.fromisoformat(row["date"])
        if day in dates or not (result.context.period_start <= day < result.context.period_end):
            return _report(role, "blocked", reasons=("daily_scope_mismatch",))
        dates.add(day)
        metric = row["metrics"]["cost"]
        if metric.get("data_status") != "complete" or metric.get("amount") is None:
            return _report(role, "unavailable", reasons=("daily_data_partial_or_missing",))
        value = decimal_number(metric["amount"])
        if value < 0:
            return _report(role, "blocked", reasons=("negative_daily_spend",))
        entries.append((day, value))
    if len(entries) < 6:
        return _report(role, "unavailable", reasons=("six_complete_days_required",))
    if sorted(dates) != [
        date.fromordinal(result.context.period_end.toordinal() - len(dates) + i)
        for i in range(len(dates))
    ]:
        return _report(role, "unavailable", reasons=("daily_calendar_gaps",))
    costs = [value for _, value in sorted(entries)]
    old = Decimal(median(costs[-6:-3]))
    recent = Decimal(median(costs[-3:]))
    if old <= 0:
        return _report(role, "unavailable", reasons=("nonpositive_comparison_baseline",))
    large_change = abs(recent - old) / old >= Decimal("0.5")
    return _report(role, "review_required", evidence=_proof(result, "cost"),
                   reasons=("candidate_only_not_statistical_anomaly",) if large_change
                   else ("no_large_change_in_selected_window",),
                   observations={"large_spend_change_candidate": large_change,
                                 "comparison": "3_recent_complete_days_vs_3_previous_complete_days"})


def _knowledge_steward(result: AnalysisResult, profile: dict | None) -> dict:
    role = "knowledge_steward"
    if not isinstance(profile, dict) or not isinstance(profile.get("fields"), dict):
        return _report(role, "unavailable", reasons=("client_confirmed_profile_required",))
    code = profile["fields"].get("industry_code")
    if not isinstance(code, str):
        return _report(role, "unavailable", reasons=("industry_code_missing",))
    match = next((industry for industry in industries() if industry["code"] == code), None)
    if match is None:
        return _report(role, "review_required", reasons=("unclassified_industry_universal_fallback",))
    if not match.get("sources"):
        return _report(role, "unavailable", reasons=("industry_sources_missing",))
    return _report(role, "review_required",
                   reasons=("industry_process_only_no_benchmarks",),
                   observations={"industry_code": code, "knowledge_version": match["version"],
                                 "review_status": match["review_status"]})


def _challenges(result: AnalysisResult, reports: list[dict]) -> dict:
    role = "recommendation_challenger"
    reasons = ["human_action_approval_required", "causal_effect_not_established",
               "independent_evidence_authenticity_not_proven"]
    if result.context.quality_status != "complete":
        reasons.append("incomplete_or_stale_inputs")
    if not result.context.conversion_definition:
        reasons.append("conversion_definition_missing")
    if any(report["status"] == "blocked" for report in reports):
        reasons.append("specialist_blockers_present")
    if any(report["status"] == "unavailable" for report in reports):
        reasons.append("some_specialists_lack_sources")
    return _report(role, "blocked", reasons=tuple(reasons))


def chief_analyze(result: AnalysisResult, *, daily: tuple[dict, ...] = (),
                  profile: dict | None = None) -> dict:
    """Route ONLY suitable specialists; return a read-only structured diagnostic.

    No extra source connector is inferred: search terms, landing funnels and CRM
    cohorts are absent from the sealed campaign snapshot. They remain unavailable.
    The verification status is conservative even with a complete snapshot.
    """
    # Revalidate strict source/evidence scope even if caller already has an object.
    result = AnalysisResult.model_validate(result.model_dump())
    quality = result.context.quality_status
    if len(result.sources) == 0 or not result.evidence:
        raise ValueError("trusted_source_required")
    if quality == "unknown":
        # Unknown quality must never silently become complete.
        return {
            "status": "blocked", "reason_codes": ["unknown_source_quality"],
            "specialists": [], "chief": "chief_analyst",
            "publication_allowed": False, "advertising_write_allowed": False,
        }
    reports = [
        _tracking_integrity(result),
        _lead_quality(result),
        _anomaly_sentinel(result, daily),
        _knowledge_steward(result, profile),
        _report("search_intent", "unavailable", reasons=("search_query_source_not_connected",)),
        _report("landing_cro", "unavailable", reasons=("landing_funnel_source_not_connected",)),
        _report("customer_value", "unavailable", reasons=("crm_cohort_source_not_connected",)),
    ]
    reports.append(_challenges(result, reports))
    if {report["role"] for report in reports} != set(ADDITIONAL_AGENTS):
        raise ValueError("agent_dispatch_coverage")
    return {
        "chief": "chief_analyst",
        "status": "blocked" if quality in ("partial", "stale")
                  else "review_required",
        "reason_codes": ["read_only_diagnostic_not_action_plan",
                         "model_not_used", "source_authenticity_requires_service_review"],
        "specialists": reports,
        "source_refs": [source.id for source in result.sources],
        "evidence_count": len(result.evidence),
        "currency": result.context.currency,
        "period": {"from": result.context.period_start.isoformat(),
                   "to_exclusive": result.context.period_end.isoformat()},
        "quality_status": quality,
        "external_llm": False, "publication_allowed": False,
        "advertising_write_allowed": False, "independent_review_verified": False,
    }
