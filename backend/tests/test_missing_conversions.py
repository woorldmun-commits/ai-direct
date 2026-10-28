from dataclasses import replace
from datetime import timedelta

import pytest

from app.rules.domain import AuditSettings, NotEnoughData, Reason, run
from app.rules.high_cpa import HIGH_CPA_BASELINE, HIGH_CPA_TARGET
from test_rule_high_cpa import D, TARGET, snap


@pytest.mark.parametrize('rule,settings,day,reason', [
    (HIGH_CPA_TARGET, TARGET, D, Reason.SOURCE_MISSING),
    (HIGH_CPA_BASELINE, AuditSettings(), D-timedelta(days=8), Reason.BASELINE_DATA_INSUFFICIENT),
])
def test_unknown_conversion_day_never_becomes_known_zero(rule, settings, day, reason):
    source = snap()
    source = replace(source, campaign_days=tuple(replace(row, conversions=None) if row.date == day else row
                                                 for row in source.campaign_days))
    result, = run(rule, source, settings)
    assert isinstance(result, NotEnoughData)
    assert result.reason == reason


def test_zero_conversion_rule_does_not_use_incomplete_baseline():
    from app.rules.zero_conv_campaign import ZERO_CONV_CAMPAIGN
    source = snap(eval_conv=0)
    source = replace(source, campaign_days=tuple(replace(row, conversions=None) if row.date == D-timedelta(days=8) else row
                                                 for row in source.campaign_days))
    result, = run(ZERO_CONV_CAMPAIGN, source, AuditSettings())
    assert result.reference_type == 'absolute'


def test_placement_reference_rejects_unknown_campaign_conversions():
    from app.rules.zero_conv_placements import ZERO_CONV_PLACEMENTS, _reference
    from app.rules.domain import windows
    source = snap()
    rows = [replace(source.campaign_days[0], conversions=None), *source.campaign_days[1:]]
    assert _reference(ZERO_CONV_PLACEMENTS, source, AuditSettings(), rows, windows(D)[0]) == Reason.SOURCE_MISSING
