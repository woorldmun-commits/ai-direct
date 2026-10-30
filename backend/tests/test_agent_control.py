"""Synthetic-only checks for an offline, non-authoritative agent review gate."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.agents.supervisor import Manifest, Submission
from app.intelligence.agent_control import (
    CHIEF,
    INDEX,
    PRODUCERS,
    REGISTRY,
    SPECIALISTS,
    Handoff,
    review_handoff,
    validate_registry,
)

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
FACT = {
    "id": "e1",
    "workspace_id": 14,
    "metric": "cost",
    "source_id": "record_1",
    "source_version": "snapshot@1",
    "source_sha256": "a" * 64,
    "captured_at": "2026-10-30T11:59:00Z",
    "value": {
        "amount": "200.00",
        "unit": "rub",
        "source": "yandex_direct",
        "period_from": "2026-10-26",
        "period_to": "2026-10-27",
        "calculation_type": "actual",
        "data_status": "complete",
        "data_sufficiency": "sufficient",
        "snapshot_id": 9,
    },
}


def manifest(fact=None):
    return Manifest.model_validate({
        "schema_version": 1,
        "synthetic": True,
        "workspace_id": 14,
        "period_from": "2026-10-26",
        "period_to": "2026-10-27",
        "max_age_seconds": 300,
        "evidence": [fact if fact is not None else deepcopy(FACT)],
    })


def submission(fact=None, *, synthetic=True):
    return Submission.model_validate({
        "schema_version": 1,
        "synthetic": synthetic,
        "claims": [fact if fact is not None else deepcopy(FACT)],
    })


def handoff(**changes):
    base = {
        "schema_version": 1,
        "specialist": "finance",
        "workspace_id": 14,
        "candidate": submission(),
        "evidence_review": submission(),
        "risk_review": submission(),
        "requests_advertising_write": False,
    }
    base.update(changes)
    return Handoff.model_validate(base)


def test_roster_is_acyclic_read_only_and_explicit():
    validate_registry()
    assert CHIEF.code == "chief_analyst"
    assert len(SPECIALISTS) == 20
    assert len(REGISTRY) == len(INDEX) == 21
    assert len(PRODUCERS) == 17
    assert all(not agent.advertising_write for agent in REGISTRY)
    assert all(agent.implementation != "running" for agent in REGISTRY)
    assert INDEX["chief_analyst"].implementation == "on_demand_read_only"
    assert INDEX["recommendation_challenger"].code not in PRODUCERS
    assert {"evidence_verifier", "risk_guardian"} <= INDEX.keys()


def test_happy_path_requires_human_and_never_authorizes_publication():
    result = review_handoff(handoff(), manifest(), now=NOW)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["structural_checks"] == {
        "producer": "PASS",
        "evidence_verifier": "PASS",
        "risk_guardian": "PASS",
    }
    assert result["review_route"][-1] == "chief_analyst"
    assert result["publication_allowed"] is False
    assert result["advertising_write_allowed"] is False
    assert result["authenticity_verified"] is False
    assert result["independent_review_verified"] is False
    assert result["causality_verified"] is False


@pytest.mark.parametrize("producer", [
    "chief_analyst", "evidence_verifier", "risk_guardian", "unregistered",
])
def test_producer_cannot_self_review_or_impersonate_control_roles(producer):
    result = review_handoff(handoff(specialist=producer), manifest(), now=NOW)
    assert result["status"] == "BLOCKED"
    assert "invalid_producer" in result["issues"]


def test_advertising_writes_are_blocked_before_any_publication():
    result = review_handoff(handoff(requests_advertising_write=True), manifest(), now=NOW)
    assert result["status"] == "BLOCKED"
    assert "advertising_write_forbidden" in result["issues"]


@pytest.mark.parametrize("key,issue", [
    ("evidence_review", "evidence_review_missing"),
    ("risk_review", "risk_review_missing"),
])
def test_required_independent_review_missing(key, issue):
    result = review_handoff(handoff(**{key: None}), manifest(), now=NOW)
    assert result["status"] == "BLOCKED"
    assert issue in result["issues"]


def test_workspace_isolation():
    result = review_handoff(handoff(workspace_id=15), manifest(), now=NOW)
    assert result["status"] == "BLOCKED"
    assert "workspace_mismatch" in result["issues"]


def test_reviewer_cannot_substitute_a_different_source_or_amount():
    tampered = deepcopy(FACT)
    tampered["value"]["amount"] = "9999.00"
    result = review_handoff(handoff(evidence_review=submission(tampered)), manifest(), now=NOW)
    assert result["status"] == "NEEDS_WORK"
    assert "evidence_verifier_needs_work" in result["issues"]


def test_empty_reviewer_claim_set_cannot_pass():
    empty = Submission.model_validate({"schema_version": 1, "synthetic": True, "claims": []})
    result = review_handoff(handoff(risk_review=empty), manifest(), now=NOW)
    assert result["status"] == "BLOCKED"
    assert "risk_guardian_claim_set_mismatch" in result["issues"]


def test_missing_or_stale_evidence_stops_handoff():
    older = deepcopy(FACT)
    older["captured_at"] = "2026-10-30T09:00:00Z"
    trusted = manifest(older)
    submitted = submission(older)
    result = review_handoff(handoff(candidate=submitted, evidence_review=submitted,
                                    risk_review=submitted), trusted, now=NOW)
    assert result["status"] == "BLOCKED"
    assert "producer_blocked" in result["issues"]


def test_partial_data_is_not_approved():
    partial = deepcopy(FACT)
    partial["value"]["data_status"] = "partial"
    trusted = manifest(partial)
    submitted = submission(partial)
    result = review_handoff(handoff(candidate=submitted, evidence_review=submitted,
                                    risk_review=submitted), trusted, now=NOW)
    assert result["status"] == "NEEDS_WORK"
    assert "producer_needs_work" in result["issues"]


def test_empty_manifest_rejected_even_if_passes_schema():
    result = review_handoff(handoff(), Manifest.model_validate({
        "schema_version": 1, "synthetic": True, "workspace_id": 14,
        "period_from": "2026-10-26", "period_to": "2026-10-27",
        "max_age_seconds": 300, "evidence": [],
    }), now=NOW)
    assert result["status"] == "BLOCKED"


def test_strict_types_and_unknown_fields():
    with pytest.raises(ValidationError):
        handoff(workspace_id="14")
    with pytest.raises(ValidationError):
        handoff(requests_advertising_write="false")
    with pytest.raises(ValidationError):
        handoff(unrecognized=True)


def test_no_claims_or_missing_source_do_not_pass():
    empty = Submission.model_validate({"schema_version": 1, "synthetic": True, "claims": []})
    result = review_handoff(handoff(candidate=empty, evidence_review=empty,
                                    risk_review=empty), manifest(), now=NOW)
    assert result["status"] == "BLOCKED"
    bad = deepcopy(FACT)
    bad["id"] = "other"
    result = review_handoff(handoff(candidate=submission(bad)), manifest(), now=NOW)
    assert result["status"] == "BLOCKED"
