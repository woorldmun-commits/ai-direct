from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.intelligence.profiles import EvaluationPolicy
from app.rules.business import prepare, context_meta, history_days
from app.rules.domain import AuditSettings, CampaignDay, Finding, Reason, SnapshotView, run
from app.rules.high_cpa import HIGH_CPA_TARGET, HIGH_CPA_BASELINE
from app.audit.verification import VerificationBlocked, validate

END = date(2026, 10, 20)
DEFINITION = {'provider': 'yandex_metrika', 'counter_id': 555, 'goal_ids': [111], 'attribution': 'last'}


def profile(**policy_changes):
    return {'revision': 2, 'fields': {'industry_code': 'cosmetology', 'business_model': 'b2c',
        'crm_available': True, 'sales_cycle_days': 90,
        'evaluation_policy': {'counter_id': 555, 'goal_ids': [111], 'attribution': 'last',
            'conversion_stage': 'visit', 'conversion_lag_days': 2, 'minimum_conversions': 1, **policy_changes}}}


def snapshot(**changes):
    days = tuple(CampaignDay(10, END - timedelta(days=i), Decimal('3000'), 20, Decimal('1')) for i in range(37))
    return replace(SnapshotView(1, 2, 3, END-timedelta(days=36), END,
        frozenset({'yandex_direct', 'direct_conversions'}), days,
        partial_from=END-timedelta(days=2), conversion_definition=DEFINITION), **changes)


def test_mature_window_uses_confirmed_conversion_lag_not_sales_cycle():
    source = snapshot()
    view = prepare(source, profile())
    assert isinstance(view, SnapshotView)
    assert view.period_to == END-timedelta(days=3)
    assert view.period_from == source.period_from
    assert max(d.date for d in view.campaign_days) == view.period_to
    assert context_meta(profile(), view)['profile_revision'] == '2'


@pytest.mark.parametrize('days', [31, 60, 90, 3650])
def test_manufacturing_sale_with_immature_history_abstains(days):
    assert prepare(snapshot(), profile(conversion_stage='sale', conversion_lag_days=days)) == Reason.MATURITY_INSUFFICIENT


@pytest.mark.parametrize('key,value', [('counter_id', 777), ('goal_ids', [222]), ('attribution', 'automatic')])
def test_wrong_goal_binding_never_compares_cpa(key, value):
    assert prepare(snapshot(), profile(**{key: value})) == Reason.GOAL_MISMATCH


@pytest.mark.parametrize('stage', ['qualified_lead', 'visit', 'sale'])
def test_downstream_goal_requires_outcome_data(stage):
    data = profile(conversion_stage=stage)
    data['fields']['crm_available'] = False
    assert prepare(snapshot(), data) == Reason.OUTCOME_DATA_REQUIRED


def test_missing_policy_never_infers_lag_from_industry_or_sales_cycle():
    data = profile()
    data['fields']['evaluation_policy'] = None
    assert prepare(snapshot(), data) == Reason.BUSINESS_CONTEXT_REQUIRED


def test_unknown_partial_boundary_cannot_claim_mature_period():
    assert prepare(snapshot(partial_from=None), profile()) == Reason.MATURITY_INSUFFICIENT


def test_larger_minimum_sample_blocks_financial_finding():
    settings = AuditSettings(target_cpa=Decimal('1000'), business_profile=profile(minimum_conversions=100))
    output = run(HIGH_CPA_TARGET, snapshot(), settings)
    assert all(not isinstance(item, Finding) for item in output)
    assert output[0].reason == Reason.VOLUME_INSUFFICIENT


def test_small_sample_cannot_treat_low_cpa_as_evidence_that_problem_disappeared():
    source = snapshot()
    source = replace(source, campaign_days=tuple(replace(day, cost=Decimal('10')) for day in source.campaign_days))
    output = run(HIGH_CPA_TARGET, source, AuditSettings(Decimal('1000'), profile(minimum_conversions=100)))
    assert len(output) == 1
    assert output[0].reason == Reason.VOLUME_INSUFFICIENT
    assert output[0].object_id == 10


def test_confirmed_minimum_also_applies_to_baseline_comparison():
    source = snapshot(period_from=END-timedelta(days=39), campaign_days=tuple(
        CampaignDay(10, END-timedelta(days=i), Decimal('3000'), 20, Decimal('1')) for i in range(40)))
    mature = prepare(source, profile())
    from app.rules.domain import windows
    evaluation, _ = windows(mature.period_to)
    source = replace(source, campaign_days=tuple(replace(day, conversions=Decimal('100'))
        if day.date in evaluation else day for day in source.campaign_days))
    output = run(HIGH_CPA_BASELINE, source, AuditSettings(None, profile(minimum_conversions=100)))
    assert len(output) == 1
    assert output[0].reason == Reason.BASELINE_DATA_INSUFFICIENT


def test_same_metrics_clinic_visit_and_long_manufacturing_sale_differ():
    clinic = run(HIGH_CPA_TARGET, snapshot(), AuditSettings(Decimal('1000'), profile()))
    factory = profile(conversion_stage='sale', conversion_lag_days=90)
    factory['fields']['industry_code'] = 'manufacturing'
    factory['fields']['business_model'] = 'b2b'
    industrial = run(HIGH_CPA_TARGET, snapshot(), AuditSettings(Decimal('1000'), factory))
    assert isinstance(clinic[0], Finding)
    assert clinic[0].evidence_meta['business_policy_version'] == 'business_policy@1'
    assert industrial[0].reason == Reason.MATURITY_INSUFFICIENT


@pytest.mark.parametrize('patch', [{'conversion_lag_days': True}, {'conversion_lag_days': -1},
    {'minimum_conversions': 0}, {'goal_ids': [111, 111]}, {'goal_ids': [222, 111]},
    {'attribution': 'invented'}, {'conversion_stage': 'profit'}, {'counter_id': 0}])
def test_policy_boundary_validation(patch):
    with pytest.raises(ValidationError):
        EvaluationPolicy.model_validate(profile(**patch)['fields']['evaluation_policy'])


@pytest.mark.parametrize('field,value', [('actual', Decimal('1')), ('reference', Decimal('2')),
    ('object_id', 999), ('issue_key', b'forged'), ('action', {'type': 'increase_bid'}),
    ('evidence_meta', {'profile_revision': '900'})])
def test_publication_gate_rejects_tampered_findings(field, value):
    settings = AuditSettings(Decimal('1000'), profile())
    finding, = run(HIGH_CPA_TARGET, snapshot(), settings)
    with pytest.raises(VerificationBlocked):
        validate(snapshot(), settings, replace(finding, **{field: value}))


def test_publication_gate_accepts_reproducible_finding():
    settings = AuditSettings(Decimal('1000'), profile())
    finding, = run(HIGH_CPA_TARGET, snapshot(), settings)
    validate(snapshot(), settings, finding)


def test_publication_batch_reloads_independent_source_once_and_rejects_tampering(monkeypatch):
    from app.audit import verification
    source = snapshot()
    source = replace(source, campaign_days=source.campaign_days + tuple(
        replace(day, campaign_id=11) for day in source.campaign_days))
    settings = AuditSettings(Decimal('1000'), profile())
    findings = run(HIGH_CPA_TARGET, source, settings)
    calls = []
    class Cursor:
        def fetchone(self):
            return ({'target_cpa': '1000', 'business_profile': profile()},)
    class Connection:
        def execute(self, sql, args):
            calls.append(args)
            return Cursor()
    loads = []
    monkeypatch.setattr(verification, 'load_view', lambda conn, sid: loads.append(sid) or source)
    verifier = verification.PublicationVerifier(Connection(), 9)
    for finding in findings:
        assert verifier.verify(source.workspace_id, source.direct_account_id, source.snapshot_id, finding) == verification.VERSION
    assert len(calls) == len(loads) == 1
    with pytest.raises(VerificationBlocked):
        verifier.verify(source.workspace_id, source.direct_account_id, source.snapshot_id, replace(findings[0], actual=Decimal('1')))
    with pytest.raises(VerificationBlocked):
        verifier.verify(999, 2, 3, findings[0])


@pytest.mark.parametrize('lag,expected', [(0,40),(2,40),(7,44),(30,67),(90,127),(91,37),(3650,37)])
def test_backfill_is_bounded_and_driven_by_confirmed_lag(lag,expected):
    assert history_days(profile(conversion_lag_days=lag))==expected
    assert history_days(None)==37


def test_long_cycle_sale_can_be_analyzed_after_mature_history_backfill():
    policy=profile(conversion_stage='sale',conversion_lag_days=90)
    source=snapshot(period_from=END-timedelta(days=126),campaign_days=tuple(
        CampaignDay(10,END-timedelta(days=i),Decimal('3000'),20,Decimal('1')) for i in range(127)))
    finding,=run(HIGH_CPA_TARGET,source,AuditSettings(Decimal('1000'),policy))
    assert isinstance(finding,Finding)
    assert finding.evidence['cpa'].period.date_to==END-timedelta(days=90)
    validate(source,AuditSettings(Decimal('1000'),policy),finding)
