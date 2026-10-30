"""Confirmed goal binding and mature cohorts; no inferred industry benchmarks."""
from dataclasses import replace
from datetime import timedelta

from app.rules.domain import EVALUATION_DAYS, Reason, SnapshotView

VERSION = 'business_policy@1'


def history_days(profile):
    policy = profile['fields'].get('evaluation_policy') if profile else None
    # shortcut: automatic backfill is capped at 90 lag days; upgrade after provider-volume and retention acceptance.
    return 37 + max(3, policy['conversion_lag_days']) if policy and policy['conversion_lag_days'] <= 90 else 37


def prepare(snapshot: SnapshotView, profile) -> SnapshotView | Reason:
    fields = profile['fields']
    policy = fields.get('evaluation_policy')
    if not policy:
        return Reason.BUSINESS_CONTEXT_REQUIRED
    binding = {'provider': 'yandex_metrika', 'counter_id': policy['counter_id'],
               'goal_ids': list(policy['goal_ids']), 'attribution': policy['attribution']}
    if snapshot.conversion_definition != binding:
        return Reason.GOAL_MISMATCH
    if policy['conversion_stage'] in ('qualified_lead', 'visit', 'sale') and not fields['crm_available']:
        return Reason.OUTCOME_DATA_REQUIRED
    if snapshot.partial_from is None:
        return Reason.MATURITY_INSUFFICIENT
    end = min(snapshot.period_to-timedelta(days=policy['conversion_lag_days']),
              snapshot.partial_from-timedelta(days=1))
    if (end-snapshot.period_from).days+1 < EVALUATION_DAYS:
        return Reason.MATURITY_INSUFFICIENT
    # Baseline rules independently verify that all 30+7 mature days are covered by the sealed snapshot.
    return replace(snapshot, period_to=end,
                   campaign_days=tuple(day for day in snapshot.campaign_days if day.date <= end),
                   placement_days=tuple(day for day in snapshot.placement_days if day.date <= end))


def context_meta(profile, view):
    fields, policy = profile['fields'], profile['fields']['evaluation_policy']
    return {'business_policy_version': VERSION, 'profile_revision': str(profile['revision']),
            'industry_code': fields['industry_code'], 'business_model': fields['business_model'],
            'conversion_stage': policy['conversion_stage'], 'conversion_lag_days': str(policy['conversion_lag_days']),
            'minimum_conversions': str(policy['minimum_conversions']), 'maturity_cutoff': view.period_to.isoformat()}
