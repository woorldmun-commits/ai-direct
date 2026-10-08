"""app/flags.py — единственный читатель флагов окружения; умолчания по решению владельца."""

import pytest

from app import flags

ON = ("intelligence_v2", "source_of_truth_v2", "evidence_bundle_v2", "safety_engine_v2", "capability_registry_v2")
OFF = ("chief_analyst", "search_intelligence", "rsya_intelligence", "root_cause", "opportunity_engine",
       "creative_intelligence", "llm_enabled")


def test_defaults_follow_owner_decisions():
    active = flags.active_flags({})
    assert active == {**{n: True for n in ON}, **{n: False for n in OFF}}


@pytest.mark.parametrize("raw, want", [("0", False), ("false", False), (" OFF ", False), ("no", False),
                                       ("1", True), ("true", True), (" On ", True), ("yes", True)])
def test_env_overrides_default_both_ways(raw, want):
    assert flags.flag("intelligence_v2", {"INTELLIGENCE_V2": raw}) is want
    assert flags.flag("llm_enabled", {"LLM_ENABLED": raw}) is want


@pytest.mark.parametrize("raw", ["", "maybe", "2"])
def test_empty_or_unparseable_value_keeps_default(raw):
    assert flags.flag("llm_enabled", {"LLM_ENABLED": raw}) is False
    assert flags.flag("safety_engine_v2", {"SAFETY_ENGINE_V2": raw}) is True


def test_unknown_flag_is_an_error():
    with pytest.raises(KeyError):
        flags.flag("typo_flag", {})


def test_reads_process_environment_by_default(monkeypatch):
    monkeypatch.setenv("CHIEF_ANALYST", "1")
    assert flags.active_flags()["chief_analyst"] is True
