"""Типы утверждений и статус причинности (§17–18 ТЗ): вывод агента — не доказательство."""

import pytest

from app.intelligence.contracts.claims import (
    AI_ALLOWED_CLAIM_TYPES, AUTHORITATIVE_CLAIM_TYPES, NON_EVIDENCE_KINDS, CausalStatus, Claim, ClaimType)

C, K = ClaimType, CausalStatus


def test_claim_type_sets():
    assert AUTHORITATIVE_CLAIM_TYPES == {C.FACT, C.DERIVED_FACT}
    assert AI_ALLOWED_CLAIM_TYPES == {C.OBSERVATION, C.ASSOCIATION, C.HYPOTHESIS}
    assert NON_EVIDENCE_KINDS == {C.RECOMMENDATION_CANDIDATE, C.ANALYST_OPINION}
    assert not (AUTHORITATIVE_CLAIM_TYPES & AI_ALLOWED_CLAIM_TYPES)
    assert not (NON_EVIDENCE_KINDS & AUTHORITATIVE_CLAIM_TYPES)


@pytest.mark.parametrize("ctype", [C.FACT, C.DERIVED_FACT])
def test_agent_output_is_never_evidence(ctype):
    """AI-claim не может быть FACT/DERIVED_FACT, даже со ссылкой на evidence."""
    with pytest.raises(ValueError, match="AI"):
        Claim(ctype, "CPA вырос", ("ev1",), K.DESCRIPTIVE, origin="ai")
    with pytest.raises(ValueError, match="AI"):
        Claim(ctype, "CPA вырос", ("ev1",), K.DESCRIPTIVE)  # origin по умолчанию — ai


@pytest.mark.parametrize("ctype", [C.EXPERIMENT_RESULT, C.VERIFIED_OUTCOME])
def test_ai_cannot_claim_experiment_or_outcome(ctype):
    with pytest.raises(ValueError, match="AI"):
        Claim(ctype, "x", ("ev1",), K.DESCRIPTIVE, origin="ai")


def test_deterministic_fact_requires_evidence():
    with pytest.raises(ValueError, match="evidence"):
        Claim(C.FACT, "Расход 100 ₽", (), K.DESCRIPTIVE, origin="deterministic")
    assert Claim(C.FACT, "Расход 100 ₽", ("ev1",), K.DESCRIPTIVE, origin="deterministic").type is C.FACT
    assert Claim(C.DERIVED_FACT, "CPA 50 ₽", ("ev1", "ev2"), K.DESCRIPTIVE, origin="deterministic")


def test_ai_allowed_types_construct():
    for t in AI_ALLOWED_CLAIM_TYPES | NON_EVIDENCE_KINDS:
        assert Claim(t, "текст", ("ev1",), K.DESCRIPTIVE).origin == "ai"


def test_origin_text_and_evidence_shape_are_validated():
    with pytest.raises(ValueError):
        Claim(C.OBSERVATION, "x", (), K.DESCRIPTIVE, origin="human")
    with pytest.raises(ValueError):
        Claim(C.OBSERVATION, " ", (), K.DESCRIPTIVE)
    with pytest.raises(ValueError):
        Claim(C.OBSERVATION, "x", ["ev1"], K.DESCRIPTIVE)  # список изменяем — нужен tuple
    with pytest.raises(ValueError):
        Claim(C.OBSERVATION, "x", ("",), K.DESCRIPTIVE)


@pytest.mark.parametrize("ctype, status", [
    (C.OBSERVATION, K.ASSOCIATED), (C.OBSERVATION, K.PLAUSIBLE_HYPOTHESIS),
    (C.ASSOCIATION, K.PLAUSIBLE_HYPOTHESIS), (C.HYPOTHESIS, K.EXPERIMENTALLY_SUPPORTED),
    (C.HYPOTHESIS, K.VERIFIED), (C.ASSOCIATION, K.VERIFIED), (C.ANALYST_OPINION, K.ASSOCIATED)])
def test_causal_status_cannot_exceed_what_claim_type_allows(ctype, status):
    with pytest.raises(ValueError, match="causal"):
        Claim(ctype, "x", ("ev1",), status)


@pytest.mark.parametrize("ctype, status", [
    (C.OBSERVATION, K.DESCRIPTIVE), (C.ASSOCIATION, K.ASSOCIATED), (C.HYPOTHESIS, K.PLAUSIBLE_HYPOTHESIS),
    (C.HYPOTHESIS, K.NOT_ESTABLISHED), (C.OBSERVATION, K.NOT_ESTABLISHED)])
def test_allowed_causal_statuses(ctype, status):
    assert Claim(ctype, "x", ("ev1",), status).causal_status is status


def test_experimentally_supported_and_verified_are_deterministic_only():
    exp = Claim(C.EXPERIMENT_RESULT, "x", ("ev1",), K.EXPERIMENTALLY_SUPPORTED, origin="deterministic")
    ver = Claim(C.VERIFIED_OUTCOME, "x", ("ev1",), K.VERIFIED, origin="deterministic")
    assert exp.causal_status is K.EXPERIMENTALLY_SUPPORTED and ver.causal_status is K.VERIFIED
    with pytest.raises(ValueError, match="causal"):
        Claim(C.EXPERIMENT_RESULT, "x", ("ev1",), K.VERIFIED, origin="deterministic")
    with pytest.raises(ValueError, match="causal"):
        Claim(C.VERIFIED_OUTCOME, "x", ("ev1",), K.EXPERIMENTALLY_SUPPORTED, origin="deterministic")


def test_claim_is_frozen():
    c = Claim(C.OBSERVATION, "x", ("ev1",), K.DESCRIPTIVE)
    with pytest.raises(Exception):
        c.text = "y"
