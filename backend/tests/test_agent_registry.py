"""Agent Registry в коде (§59, §116 ТЗ) и AgentRunRecord (docs/INTELLIGENCE_V2_CONTRACTS.md §1)."""

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from app.intelligence.agents.registry import AGENTS, AgentSpec, get_agent
from app.intelligence.agents.run_record import AgentRunRecord, record_for_deterministic_run
from app.intelligence.contracts.claims import AUTHORITATIVE_CLAIM_TYPES
from app.intelligence.contracts.sufficiency import DataSufficiency

T0 = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)
HASH = "a" * 64


def test_only_the_two_placeholders_are_registered():
    assert set(AGENTS) == {"evidence_judge", "chief_analyst"}


def test_spec_fields_match_59_and_116():
    names = {f.name for f in dataclasses.fields(AgentSpec)}
    assert {"agent_id", "name", "domain", "provider_scope", "required_data", "optional_data", "allowed_claim_types",
            "allowed_actions", "forbidden_claims", "version", "knowledge_pack_version", "model_policy",
            "max_runtime_s", "max_tool_calls", "workspace_scope", "object_scope", "data_scope", "read_scope",
            "write_scope"} <= names


@pytest.mark.parametrize("agent_id", ["evidence_judge", "chief_analyst"])
def test_no_agent_can_write_or_assert_facts(agent_id):
    spec = get_agent(agent_id)
    assert spec.write_scope == ()
    assert not (spec.allowed_claim_types & AUTHORITATIVE_CLAIM_TYPES)
    assert spec.agent_id == agent_id and spec.read_scope


def test_authoritative_claims_are_rejected_at_construction():
    base = AGENTS["chief_analyst"]
    from app.intelligence.contracts.claims import ClaimType
    with pytest.raises(ValueError, match="FACT"):
        dataclasses.replace(base, allowed_claim_types=frozenset({ClaimType.FACT}))
    with pytest.raises(ValueError, match="write_scope"):
        dataclasses.replace(base, write_scope=("campaigns",))


def test_disabled_by_default_and_flag_read_at_call_time(monkeypatch):
    monkeypatch.delenv("CHIEF_ANALYST", raising=False)
    spec = get_agent("chief_analyst")
    assert spec.enabled is False and get_agent("evidence_judge").enabled is False
    monkeypatch.setenv("CHIEF_ANALYST", "true")
    assert spec.enabled is True  # тот же объект, флаг прочитан заново
    monkeypatch.setenv("CHIEF_ANALYST", "off")
    assert spec.enabled is False


def test_unknown_agent_raises():
    with pytest.raises(KeyError):
        get_agent("search_expert")


def test_registry_is_read_only():
    with pytest.raises(TypeError):
        AGENTS["x"] = AGENTS["chief_analyst"]


# --- AgentRunRecord -------------------------------------------------------------------------------

def deterministic(**kw):
    base = dict(run_id="r1", workspace_id=1, started_at=T0, completed_at=T0 + timedelta(seconds=2),
                agent_version="1", rule_version="rules@2", input_bundle_hash=HASH, source_snapshot_ids=(5,),
                metric_versions=("cpa@1",), data_status="complete", data_sufficiency=DataSufficiency.MEDIUM,
                output_hash=HASH, decision_count=1, recommendation_count=1)
    return record_for_deterministic_run(**{**base, **kw})


def test_llm_off_run_has_empty_llm_fields_and_is_valid():
    r = deterministic()
    assert (r.provider, r.model, r.model_version, r.prompt_version, r.prompt_hash) == (None,) * 5
    assert (r.knowledge_pack_version, r.knowledge_pack_hash) == (None, None)
    assert r.status == "completed" and r.explanation_count == 0


def test_run_record_fields_follow_contract():
    names = {f.name for f in dataclasses.fields(AgentRunRecord)}
    assert {"run_id", "workspace_id", "analysis_run_id", "started_at", "completed_at", "status", "agent_version",
            "rule_version", "release_id", "provider", "model", "model_version", "prompt_version", "prompt_hash",
            "knowledge_pack_version", "knowledge_pack_hash", "input_bundle_hash", "source_snapshot_ids",
            "metric_versions", "business_context_version", "analysis_plan_id", "capabilities_used", "tools_used",
            "latency_ms", "output_hash", "decision_count", "recommendation_count", "explanation_count",
            "data_status", "data_sufficiency", "refusal_reason", "error_code"} <= names


def test_run_record_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        deterministic().status = "failed"


def full_llm(**kw):
    llm = dict(provider="anthropic", model="m", model_version="1", prompt_version="p@1", prompt_hash=HASH,
               knowledge_pack_version="kp@1", knowledge_pack_hash=HASH)
    return dataclasses.replace(deterministic(), **{**llm, **kw})


def test_llm_run_needs_prompt_hash_and_model():
    assert full_llm().provider == "anthropic"
    for missing in ("model", "prompt_version", "prompt_hash"):
        with pytest.raises(ValueError, match="llm"):
            full_llm(**{missing: None})


def test_llm_fields_without_provider_rejected():
    with pytest.raises(ValueError, match="llm"):
        dataclasses.replace(deterministic(), prompt_hash=HASH)


@pytest.mark.parametrize("kw", [
    {"input_bundle_hash": "xyz"}, {"output_hash": "A" * 64}, {"decision_count": -1},
    {"started_at": datetime(2026, 10, 8)},                               # без пояса
    {"completed_at": T0 - timedelta(seconds=1)},
    {"workspace_id": 0}, {"data_status": "unknown"}, {"run_id": ""}])
def test_run_record_validation(kw):
    with pytest.raises(ValueError):
        deterministic(**kw)


def test_status_requires_matching_reason():
    with pytest.raises(ValueError, match="refusal_reason"):
        dataclasses.replace(deterministic(), status="refused")
    with pytest.raises(ValueError, match="error_code"):
        dataclasses.replace(deterministic(), status="failed")
    with pytest.raises(ValueError):
        dataclasses.replace(deterministic(), refusal_reason="x")  # completed с причиной отказа
    assert dataclasses.replace(deterministic(), status="refused", refusal_reason="insufficient_data",
                               output_hash=None).status == "refused"
