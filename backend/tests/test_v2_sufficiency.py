"""Достаточность данных и уровень действия v2 (§19–20 ТЗ): причина обязательна, уровень только понижается."""

from decimal import Decimal

import pytest

from app.intelligence.contracts.sufficiency import (
    ActionLevel, DataSufficiency, SufficiencyAssessment, from_legacy_action_level, from_legacy_data_quality,
    from_legacy_data_sufficiency, level_for, lowered, to_legacy_action_level, to_legacy_data_quality,
    to_legacy_data_sufficiency)

S, A = DataSufficiency, ActionLevel


@pytest.mark.parametrize("sufficiency, level", [(S.INSUFFICIENT, A.NO_ACTION), (S.LOW, A.INSPECT_ONLY),
                                                (S.MEDIUM, A.REVIEW), (S.HIGH, A.CHANGE_CANDIDATE)])
def test_sufficiency_maps_to_action_level_per_spec_20(sufficiency, level):
    assert level_for(sufficiency) is level


def test_levels_are_ordered_by_impact():
    order = [A.NO_ACTION, A.INSPECT_ONLY, A.REVIEW, A.CHANGE_CANDIDATE]
    assert sorted(reversed(order), key=lambda x: x.rank) == order


@pytest.mark.parametrize("a", list(A))
@pytest.mark.parametrize("b", list(A))
def test_lowered_never_exceeds_either_argument(a, b):
    result = lowered(a, b)
    assert result.rank <= a.rank and result.rank <= b.rank and result in (a, b)


def test_lowered_picks_the_smaller():
    assert lowered(A.CHANGE_CANDIDATE, A.REVIEW) is A.REVIEW
    assert lowered(A.NO_ACTION, A.CHANGE_CANDIDATE) is A.NO_ACTION


def test_assessment_requires_non_empty_reason():
    for bad in ("", "   "):
        with pytest.raises(ValueError, match="reason"):
            SufficiencyAssessment(S.MEDIUM, bad)
    ok = SufficiencyAssessment(S.MEDIUM, "7 дней, 312 кликов, 4 конверсии", days=7, clicks=312,
                               conversions=Decimal("4"))
    assert ok.action_level is A.REVIEW


def test_assessment_facts_are_validated():
    with pytest.raises(ValueError):
        SufficiencyAssessment(S.LOW, "x", conversions=1.5)  # float вместо Decimal
    with pytest.raises(ValueError):
        SufficiencyAssessment(S.LOW, "x", days=-1)
    with pytest.raises(ValueError):
        SufficiencyAssessment(S.LOW, "x", clicks=True)


def test_legacy_action_level_roundtrip_and_change_naming():
    assert from_legacy_action_level("change") is A.CHANGE_CANDIDATE
    assert to_legacy_action_level(A.CHANGE_CANDIDATE) == "change"
    for legacy in ("inspect_only", "review", "change"):
        assert to_legacy_action_level(from_legacy_action_level(legacy)) == legacy


def test_legacy_action_level_has_no_guess():
    with pytest.raises(ValueError):
        from_legacy_action_level("change_candidate")  # это словарь v2, не БД
    with pytest.raises(ValueError):
        from_legacy_action_level("pause")
    with pytest.raises(ValueError):
        to_legacy_action_level(A.NO_ACTION)  # в БД такого уровня нет


def test_legacy_data_quality_mapping():
    for q in ("high", "medium", "low"):
        assert to_legacy_data_quality(from_legacy_data_quality(q)) == q
    with pytest.raises(ValueError):
        from_legacy_data_quality("unknown")
    with pytest.raises(ValueError):
        to_legacy_data_quality(S.INSUFFICIENT)  # у data_quality нет «insufficient»


def test_legacy_data_sufficiency_mapping():
    assert to_legacy_data_sufficiency(S.INSUFFICIENT) == "insufficient"
    assert all(to_legacy_data_sufficiency(s) == "sufficient" for s in (S.LOW, S.MEDIUM, S.HIGH))
    assert from_legacy_data_sufficiency("insufficient", None) is S.INSUFFICIENT
    assert from_legacy_data_sufficiency("sufficient", "medium") is S.MEDIUM
    with pytest.raises(ValueError):
        from_legacy_data_sufficiency("sufficient", None)  # уровень по «sufficient» не угадывается
    with pytest.raises(ValueError):
        from_legacy_data_sufficiency("maybe", "high")
