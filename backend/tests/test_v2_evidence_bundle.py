"""Evidence Bundle (§96) и AgentFinding (§60): канонический хеш и запрет «эссе»."""

import dataclasses
from datetime import date
from decimal import Decimal

import pytest

from app.intelligence.contracts.claims import CausalStatus, Claim, ClaimType
from app.intelligence.contracts.evidence import EvidenceBundle, canonical_json
from app.intelligence.contracts.finding import AgentFinding
from app.intelligence.contracts.sufficiency import DataSufficiency, SufficiencyAssessment


def bundle(**kw):
    base = dict(facts=({"id": "f1", "amount": Decimal("100.00")}, {"id": "f2", "amount": Decimal("3")}),
                findings=({"id": "x", "level": "review"},), metrics=({"metric": "cpa@1"},),
                constraints=("no_budget_change",), data_health={"stale": False, "source_failed": False},
                capabilities={"cpa": "supported", "roas": "unsupported"},
                period={"from": date(2026, 9, 1), "to": date(2026, 9, 7)},
                source_registry={"yandex_direct": "campaigns.get@v5", "yandex_metrika": "reports"})
    return EvidenceBundle(**{**base, **kw})


def test_hash_is_sha256_hex_and_stable():
    h = bundle().bundle_hash
    assert len(h) == 64 and int(h, 16) >= 0 and h == bundle().bundle_hash


def test_same_content_different_insertion_order_gives_same_hash():
    a = bundle()
    b = bundle(facts=tuple(reversed(a.facts)),
               capabilities={"roas": "unsupported", "cpa": "supported"},
               source_registry={"yandex_metrika": "reports", "yandex_direct": "campaigns.get@v5"},
               data_health={"source_failed": False, "stale": False})
    assert a.bundle_hash == b.bundle_hash


@pytest.mark.parametrize("change", [
    {"facts": ({"id": "f1", "amount": Decimal("100.01")}, {"id": "f2", "amount": Decimal("3")})},
    {"constraints": ()},
    {"capabilities": {"cpa": "partial", "roas": "unsupported"}},
    {"period": {"from": date(2026, 9, 1), "to": date(2026, 9, 8)}},
    {"data_health": {"stale": True, "source_failed": False}},
])
def test_any_change_changes_hash(change):
    assert bundle(**change).bundle_hash != bundle().bundle_hash


def test_float_is_rejected():
    with pytest.raises(ValueError, match="float"):
        bundle(facts=({"id": "f1", "amount": 100.0},))
    with pytest.raises(ValueError, match="float"):
        canonical_json({"a": [1, {"b": 0.5}]})


def test_canonical_json_form():
    assert canonical_json({"a": Decimal("1.50")}) == '{"a":{"$dec":"1.5"}}'
    assert canonical_json({"b": 1, "a": None, "c": True}) == '{"a":null,"b":1,"c":true}'


def test_non_finite_decimal_and_unknown_types_rejected():
    with pytest.raises(ValueError):
        canonical_json({"a": Decimal("NaN")})
    with pytest.raises(ValueError):
        canonical_json({"a": object()})


def test_bundle_is_frozen_and_copies_input():
    caps = {"cpa": "supported"}
    b = bundle(capabilities=caps)
    before = b.bundle_hash
    caps["cpa"] = "unsupported"
    assert b.bundle_hash == before
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.facts = ()
    with pytest.raises(TypeError):
        b.capabilities["cpa"] = "x"


# --- AgentFinding ---------------------------------------------------------------------------------

def finding(**kw):
    base = dict(agent_id="evidence_judge", agent_version="1", knowledge_version="kp@1", scope="campaign:1",
                evidence_ids=("ev1",),
                observations=(Claim(ClaimType.OBSERVATION, "CPA вырос", ("ev1",), CausalStatus.DESCRIPTIVE),),
                hypotheses=(Claim(ClaimType.HYPOTHESIS, "Сдвиг мобильного трафика", ("ev1",),
                                  CausalStatus.PLAUSIBLE_HYPOTHESIS),),
                causal_status=CausalStatus.PLAUSIBLE_HYPOTHESIS,
                data_sufficiency=SufficiencyAssessment(DataSufficiency.MEDIUM, "7 дней, 4 конверсии"),
                affected_objects=("campaign:1",), candidate_actions=(), rejected_actions=(),
                missing_data=("revenue",), next_checks=("проверить долю мобильного трафика",))
    return AgentFinding(**{**base, **kw})


def test_valid_finding_is_structured_data_without_essay_field():
    names = {x.name for x in dataclasses.fields(finding())}
    assert not names & {"text", "essay", "summary", "answer", "narrative"}
    assert names == {"agent_id", "agent_version", "knowledge_version", "scope", "evidence_ids", "observations",
                     "hypotheses", "causal_status", "data_sufficiency", "affected_objects", "candidate_actions",
                     "rejected_actions", "missing_data", "next_checks"}


def test_finding_rejects_authoritative_claims():
    fact = Claim(ClaimType.FACT, "Расход 1", ("ev1",), CausalStatus.DESCRIPTIVE, origin="deterministic")
    with pytest.raises(ValueError, match="FACT"):
        finding(observations=(fact,))


def test_finding_observation_and_hypothesis_slots_are_typed():
    with pytest.raises(ValueError, match="observations"):
        finding(observations=finding().hypotheses)
    with pytest.raises(ValueError, match="hypotheses"):
        finding(hypotheses=finding().observations)


def test_finding_claims_must_cite_finding_evidence():
    with pytest.raises(ValueError, match="evidence"):
        finding(evidence_ids=())
    other = Claim(ClaimType.OBSERVATION, "x", ("ev9",), CausalStatus.DESCRIPTIVE)
    with pytest.raises(ValueError, match="evidence"):
        finding(observations=(other,))


def test_finding_requires_tuples_and_ids():
    with pytest.raises(ValueError):
        finding(missing_data=["revenue"])
    with pytest.raises(ValueError):
        finding(agent_id="")
