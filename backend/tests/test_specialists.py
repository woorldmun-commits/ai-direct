"""Специалисты Chief Analyst: каждое семейство правил — ровно у одного специалиста, статус области честный
(«не проверялось» ≠ «проблем нет»), находки не теряются и не придумываются."""

from datetime import date
from decimal import Decimal

import pytest

from app.intelligence.agents import chief
from app.intelligence.agents.registry import AGENTS, SPECIALISTS
from app.intelligence.agents.specialists import Status, route
from app.intelligence.contracts.evidence import EvidenceBundle
from app.rules import ALL_RULES

ON = {"CHIEF_ANALYST": "1"}
CTX = chief.RunContext(run_id="run_1", workspace_id=7, rule_version="rules@2", source_snapshot_ids=(11,),
                       metric_versions=("cpa@1",), data_status="complete")


def finding(fid, rule, obj="c1"):
    return {"id": fid, "rule": rule, "object": obj, "action_type": "inspect", "exposure": Decimal(100),
            "data_sufficiency": "high", "action_level": "review"}


def bundle(*findings, sufficiency="high", rules_run=(), **health):
    return EvidenceBundle(facts=(), findings=findings, metrics=(), constraints=(),
                          data_health={"data_sufficiency": sufficiency, "rules_run": list(rules_run), **health},
                          capabilities={}, period={"from": date(2026, 9, 1)}, source_registry={})


def by_id(reports):
    return {r.agent_id: r for r in reports}


def test_every_rule_family_has_exactly_one_specialist():
    owners = [f for s in SPECIALISTS for f in s.rule_families]
    assert sorted(owners) == sorted(set(owners))
    assert {r.family for r in ALL_RULES} == set(owners)


def test_specialists_are_registered_read_only_and_off_with_chief():
    for spec in SPECIALISTS:
        assert AGENTS[spec.agent_id] is spec
        assert spec.write_scope == () and spec.flag_name == "chief_analyst"


def test_findings_go_to_their_specialist():
    b = bundle(finding("e1", "high_cpa_target@2"), finding("e2", "zero_conv_placements@2", "c2"),
               rules_run=("high_cpa_target@2", "zero_conv_placements@2"))
    reports = by_id(route(b))
    assert reports["campaign_performance"].status is Status.ISSUE_FOUND
    assert reports["campaign_performance"].finding_ids == ("e1",)
    assert reports["rsya_placements"].finding_ids == ("e2",)


def test_rule_not_run_is_not_supported_not_clean():
    reports = by_id(route(bundle(rules_run=("high_cpa_target@2",))))
    assert reports["campaign_performance"].status is Status.NO_MATERIAL_ISSUE
    assert reports["search_queries"].status is Status.NOT_SUPPORTED


def test_insufficient_data_is_not_clean():
    reports = by_id(route(bundle(sufficiency="insufficient", rules_run=("high_cpa_target@2",))))
    assert reports["campaign_performance"].status is Status.INSUFFICIENT_DATA
    assert reports["data_quality"].status is Status.INSUFFICIENT_DATA


def test_data_quality_reports_missing_sources():
    reports = by_id(route(bundle(missing=["metrika_missing"])))
    assert reports["data_quality"].status is Status.ISSUE_FOUND
    assert reports["data_quality"].missing == ("metrika_missing",)


def test_unknown_rule_is_an_error_not_a_silent_drop():
    with pytest.raises(ValueError, match="no_such_rule"):
        route(bundle(finding("e1", "no_such_rule@1")))


def test_chief_result_carries_specialist_reports():
    result = chief.run(bundle(finding("e1", "high_cpa_target@2"), rules_run=("high_cpa_target@2",)), CTX, env=ON)
    assert by_id(result.specialists)["campaign_performance"].finding_ids == ("e1",)
