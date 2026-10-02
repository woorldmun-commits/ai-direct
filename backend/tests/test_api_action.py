"""Форма action в API (API_CONTRACT.md §5): ровно четыре типа трёх правил v1.0, execution всегда manual; всё, что
вне контракта, — ошибка сервера, а не незнакомая клиенту форма. Без БД."""

from decimal import Decimal

import pytest

from app.api.serialize import action
from app.rules.zero_conv_campaign import CHECKS


@pytest.mark.parametrize("raw, meta, expected", [
    ({"type": "decrease_bid", "change_pct": -15}, {},
     {"type": "decrease_bid", "execution": "manual", "change_pct": "-15.00"}),
    ({"type": "decrease_bid", "change_pct": Decimal("-7.5")}, {},
     {"type": "decrease_bid", "execution": "manual", "change_pct": "-7.50"}),
    ({"type": "investigate_zero_conversions", "check": list(CHECKS)}, {},
     {"type": "investigate_zero_conversions", "execution": "manual", "checks": list(CHECKS), "suggest": None}),
    ({"type": "investigate_zero_conversions", "check": list(CHECKS), "suggest": "set_target_cpa"}, {},
     {"type": "investigate_zero_conversions", "execution": "manual", "checks": list(CHECKS),
      "suggest": "set_target_cpa"}),
    ({"type": "investigate_cpa_growth", "suggest": "set_target_cpa"}, {},
     {"type": "investigate_cpa_growth", "execution": "manual", "suggest": "set_target_cpa"}),
    ({"type": "exclude_placements", "execution": "manual", "placement_ids": [11, 22]},
     {"placement_11_name": "bad-site.ru", "placement_22_status": "partial"},
     {"type": "exclude_placements", "execution": "manual", "placements_count": 2,
      "placements": [{"id": "11", "name": "bad-site.ru"}, {"id": "22", "name": None}]}),
])
def test_action_shapes(raw, meta, expected):
    assert action(raw, meta) == expected


@pytest.mark.parametrize("raw", [
    {"type": "pause"},                                                     # тип вне v1.0
    {"type": "decrease_bid"},                                              # без change_pct
    {"type": "decrease_bid", "change_pct": 10},                            # «снизить» на положительный процент
    {"type": "investigate_zero_conversions", "check": ["call_the_client"]},
    {"type": "investigate_zero_conversions", "check": []},
    {"type": "investigate_cpa_growth", "suggest": "pause_campaign"},
    {"type": "exclude_placements", "placement_ids": []},
    {"type": "exclude_placements", "execution": "api", "placement_ids": [1]},
])
def test_action_outside_contract_is_rejected(raw):
    with pytest.raises((ValueError, KeyError)):
        action(raw, {})
