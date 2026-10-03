"""Форма action в API (API_CONTRACT.md §5): действие ≠ кандидат правила — API отдаёт действие уровня политики.
inspect_only → «проверить» (investigate); decrease_bid при неизвестной / не ручной стратегии → рычаги по стратегии
(lower_cpa), а не «только ставка»; exclude_placements на review — исключить вручную. Неизвестная форма — action = null
и предупреждение в лог, а не 500 на весь список. Без БД."""

import logging
from decimal import Decimal

import pytest

from app.api.serialize import action
from app.audit.present import present_action, title
from app.rules.zero_conv_campaign import CHECKS

META = {"placement_11_name": "bad-site.ru", "placement_22_status": "partial"}
PLACEMENTS = [{"id": "11", "name": "bad-site.ru"}, {"id": "22", "name": None}]
EXCLUDE = {"type": "exclude_placements", "execution": "manual", "placement_ids": [11, 22]}
LEVERS_UNKNOWN = [{"strategy": "manual", "lever": "decrease_bid", "change_pct": "-15.00"},
                  {"strategy": "auto", "lever": "lower_target_cpa", "change_pct": None},
                  {"strategy": "auto", "lever": "check_conversion_goals", "change_pct": None}]


def inv(topic, checks, suggest=None, placements=None):
    return {"type": "investigate", "topic": topic, "checks": checks, "suggest": suggest, "placements": placements,
            "execution": "manual"}


@pytest.mark.parametrize("raw, level, topic, expected", [
    # review + неизвестная стратегия: не «только ставка», а рычаги по стратегии
    ({"type": "decrease_bid", "change_pct": -15}, "review", "high_cpa",
     {"type": "lower_cpa", "strategy": "unknown", "levers": LEVERS_UNKNOWN, "execution": "manual"}),
    # inspect_only: кандидат «снизить ставку» показывается как «проверить»
    ({"type": "decrease_bid", "change_pct": Decimal("-7.5")}, "inspect_only", "high_cpa",
     inv("high_cpa", ["conversion_goals", "strategy", "search_queries_negative_keywords", "network_placements"])),
    ({"type": "investigate_zero_conversions", "check": list(CHECKS)}, "inspect_only", "zero_conv_campaign",
     inv("zero_conv_campaign", list(CHECKS))),
    ({"type": "investigate_zero_conversions", "check": list(CHECKS), "suggest": "set_target_cpa"}, "inspect_only",
     "zero_conv_campaign", inv("zero_conv_campaign", list(CHECKS), "set_target_cpa")),
    ({"type": "investigate_cpa_growth", "suggest": "set_target_cpa"}, "inspect_only", "high_cpa",
     inv("high_cpa", ["conversion_goals", "strategy", "search_queries_negative_keywords", "network_placements"],
         "set_target_cpa")),
    (EXCLUDE, "review", "zero_conv_placements",
     {"type": "exclude_placements", "placements_count": 2, "placements": PLACEMENTS, "execution": "manual"}),
    # мало данных: не «исключить», а «проверить площадки» — с их именами
    (EXCLUDE, "inspect_only", "zero_conv_placements",
     inv("zero_conv_placements", ["network_placements"], placements=PLACEMENTS)),
])
def test_action_matches_policy_level(raw, level, topic, expected):
    assert action(raw, META, level, topic) == expected


def test_bid_only_with_known_manual_strategy_on_change():
    raw = {"type": "decrease_bid", "change_pct": -15}
    assert present_action(raw, "change", "high_cpa", {}, "manual") == {
        "type": "decrease_bid", "change_pct": "-15.00", "execution": "manual"}
    for strategy, level in (("unknown", "change"), ("auto", "change"), ("manual", "review"), ("auto", "review")):
        out = present_action(raw, level, "high_cpa", {}, strategy)
        assert out["type"] == "lower_cpa"
        if strategy == "auto":  # не ручная стратегия — ставки среди рычагов нет вовсе
            assert all(lv["lever"] != "decrease_bid" for lv in out["levers"])


@pytest.mark.parametrize("raw, level", [
    ({"type": "pause"}, "review"),                                                      # тип вне v1.0
    ({"type": "decrease_bid"}, "review"),                                               # без change_pct
    ({"type": "decrease_bid", "change_pct": 10}, "review"),                             # «снизить» на +10%
    ({"type": "decrease_bid", "change_pct": 10}, "inspect_only"),
    ({"type": "investigate_zero_conversions", "check": ["call_the_client"]}, "inspect_only"),
    ({"type": "investigate_cpa_growth", "suggest": "pause_campaign"}, "inspect_only"),
    ({"type": "exclude_placements", "placement_ids": []}, "review"),
    ({"type": "exclude_placements", "execution": "api", "placement_ids": [1]}, "review"),
    ({"type": "decrease_bid", "change_pct": -15}, "approve"),                           # уровень вне политики
])
def test_action_outside_contract_is_null_and_logged(raw, level, caplog):
    with pytest.raises((ValueError, KeyError)):
        present_action(raw, level, "high_cpa", {})
    with caplog.at_level(logging.WARNING, logger="app.api"):
        assert action(raw, {}, level, "high_cpa") is None
    assert "action outside contract" in caplog.text


@pytest.mark.parametrize("topic, meta, insufficient, expected", [
    ("high_cpa", {"actual": "4820.00", "reference": "3000", "reference_type": "target"}, False,
     "CPA 4 820 ₽ выше целевого 3 000 ₽ · кампания 51234567"),
    ("high_cpa", {"actual": "2500.50", "reference": "2000.00", "reference_type": "baseline"}, False,
     "CPA 2 500,50 ₽ выше обычного 2 000 ₽ · кампания 51234567"),
    ("zero_conv_campaign", {"actual": "42000.00"}, False, "Расход 42 000 ₽ без конверсий · кампания 51234567"),
    ("zero_conv_placements", {"actual": "8000.00", "placement_ids": "1,2"}, False,
     "Площадки РСЯ без конверсий (2): 8 000 ₽ · кампания 51234567"),
    ("zero_conv_placements", {"actual": "8000.00"}, True,
     "Площадки РСЯ без конверсий · кампания 51234567 · недостаточно данных для проверки"),
    ("new_rule", {}, False, "new_rule · кампания 51234567"),
])
def test_title_is_generated_from_finding(topic, meta, insufficient, expected):
    assert title(topic, "campaign", 51234567, meta, insufficient=insufficient) == expected
