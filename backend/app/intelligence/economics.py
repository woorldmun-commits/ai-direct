"""Versioned Decimal arithmetic, with evidence; never an advertising execution or causal model."""
import hashlib
from collections.abc import Mapping, Sequence
from decimal import Decimal

from app.intelligence.contracts import (
    AnalysisContext, AnalysisResult, Evidence, MetricValue, RCAResult, SourceReference, decimal_number, validate_sources,
)

INPUT_UNITS = {
    'cost': 'money', 'impressions': 'count', 'clicks': 'count', 'conversions': 'count', 'leads': 'count',
    'qualified_leads': 'count', 'sales': 'count', 'new_customers': 'count', 'attributed_revenue': 'money',
    'net_revenue': 'money', 'cogs': 'money', 'other_variable_costs': 'money',
}
# key, numerator, denominator, multiplier, unit; CVR is displayed in percent, not the RCA fraction.
RATIOS = (
    ('ctr', 'clicks', 'impressions', 100, 'pct'), ('cpc', 'cost', 'clicks', 1, 'money'),
    ('cvr', 'conversions', 'clicks', 100, 'pct'), ('cpl', 'cost', 'leads', 1, 'money'),
    ('cpql', 'cost', 'qualified_leads', 1, 'money'), ('cpa', 'cost', 'conversions', 1, 'money'),
    ('cpa_sale', 'cost', 'sales', 1, 'money'), ('paid_cac', 'cost', 'new_customers', 1, 'money'),
    ('roas', 'attributed_revenue', 'cost', 1, 'ratio'), ('drr', 'cost', 'attributed_revenue', 100, 'pct'),
    ('gross_margin', 'gross_profit', 'net_revenue', 100, 'pct'),
)


def _metric(context, metric_id, value, unit, refs, reason=None, status='actual'):
    return MetricValue(
        metric_id=metric_id, value=value, unit=unit, currency=context.currency if unit == 'money' else None,
        status='unavailable' if value is None else status, reason_code=reason, source_refs=refs,
        period_start=context.period_start, period_end=context.period_end, timezone=context.timezone,
        as_of=context.as_of, completeness=context.completeness, sample_size=context.sample_size,
        attribution_model=context.attribution_model, attribution_window=context.attribution_window,
        conversion_definition=context.conversion_definition, cost_definition=context.cost_definition,
        calculation_version=context.calculation_version,
        quality_status=context.quality_status)


def _evidence(context, metric, sources, formula=None, inputs=(), *, limitations=()):
    identity = '|'.join((context.model_dump_json(), metric.metric_id, *metric.source_refs))
    eid = 'ev_' + hashlib.sha256(identity.encode()).hexdigest()[:24]
    return Evidence(
        id=eid, workspace_id=context.workspace_id, claim_id=metric.metric_id,
        kind='unavailable' if metric.value is None else 'derived_fact' if formula else 'observed_fact',
        source_refs=metric.source_refs,
        input_ids=tuple(ref for source in sources for ref in (source.raw_record_refs or (source.id,))),
        metric_refs=tuple(inputs), formula=formula, algorithm_version=context.calculation_version,
        generated_at=context.as_of, period_start=metric.period_start, period_end=metric.period_end,
        timezone=metric.timezone, quality_status=metric.quality_status, limitations=limitations, output=metric)


def calculate_metrics(context: AnalysisContext, inputs: Mapping[str, Decimal | int | str | None],
                      sources: Sequence[SourceReference]) -> AnalysisResult:
    """Inputs are already scoped aggregates; row deduplication belongs to the source/import boundary."""
    validate_sources(context, sources)
    if set(inputs) - INPUT_UNITS.keys():
        raise ValueError('unknown_metric_input')
    raw = {key: decimal_number(value) for key, value in inputs.items()}
    if any(value is not None and value < 0 and key != 'net_revenue' for key, value in raw.items()):
        raise ValueError('negative_metric_input')
    if any(value is not None for value in raw.values()) and not sources:
        raise ValueError('source_reference_required')
    # These are event counts, while attributed conversions may legitimately be fractional.
    if any(raw.get(key) is not None and raw[key] != raw[key].to_integral_value()
           for key in ('impressions', 'clicks', 'leads', 'qualified_leads', 'sales', 'new_customers')):
        raise ValueError('integer_count_required')
    qualities = {context.quality_status, *(source.quality_status for source in sources)}
    quality = next(q for q in ('stale', 'partial', 'unknown', 'complete') if q in qualities)
    context = context.model_copy(update={'quality_status': quality})
    refs = tuple(source.id for source in sources)
    warnings = (() if quality == 'complete' else ('data_' + quality,)) + tuple(
        field + '_missing' for field in ('cost_definition', 'conversion_definition')
        if not getattr(context, field))
    evidence, metrics = [], {}

    def put(key, value, unit, formula=None, dependencies=(), reason=None):
        metric = _metric(context, key, value, unit, refs, reason)
        metrics[key] = metric
        evidence.append(_evidence(context, metric, sources, formula, dependencies, limitations=warnings))

    for key, unit in INPUT_UNITS.items():
        value = raw.get(key)
        put(key, value, unit, reason='missing_input' if value is None else None)

    profit = None if any(raw.get(k) is None for k in ('net_revenue', 'cogs')) else raw['net_revenue'] - raw['cogs']
    put('gross_profit', profit, 'money', 'net_revenue - cogs', ('net_revenue', 'cogs'),
        'missing_input' if profit is None else None)
    contribution = (None if profit is None or any(raw.get(k) is None for k in ('other_variable_costs', 'cost'))
                    else profit - raw['other_variable_costs'] - raw['cost'])
    put('contribution_after_ads', contribution, 'money', 'net_revenue - cogs - other_variable_costs - cost',
        ('net_revenue', 'cogs', 'other_variable_costs', 'cost'), 'missing_input' if contribution is None else None)
    for key, numerator, denominator, multiplier, unit in RATIOS:
        top, bottom = metrics[numerator].value, metrics[denominator].value
        reason = 'missing_input' if top is None or bottom is None else 'nonpositive_denominator' if bottom <= 0 else None
        value = None if reason else top / bottom * multiplier
        formula = f'{numerator} / {denominator}' + (' * 100' if multiplier == 100 else '')
        put(key, value, unit, formula, (numerator, denominator), reason)
    return AnalysisResult(context=context, sources=tuple(sources), metrics=metrics, evidence=tuple(evidence), warnings=warnings)


def compare_cpa(before: AnalysisResult, after: AnalysisResult) -> RCAResult:
    """CPA2/CPA1 = (CPC2/CPC1)/(CVR2/CVR1): arithmetic explanation, never a proven root cause."""
    before, after = (AnalysisResult.model_validate(result.model_dump()) for result in (before, after))
    for result in (before, after):
        validate_sources(result.context, result.sources)
    one, two = before.context, after.context
    fields = ('workspace_id', 'account_ids', 'currency', 'timezone', 'attribution_model',
              'attribution_window', 'conversion_definition', 'cost_definition')
    conflicts = tuple('incompatible_' + field for field in fields if getattr(one, field) != getattr(two, field))
    if one.period_end > two.period_start:
        conflicts += ('overlapping_or_reversed_periods',)
    if (one.period_end - one.period_start) != (two.period_end - two.period_start):
        conflicts += ('incompatible_period_length',)
    if conflicts:
        return RCAResult(status='incompatible', metrics={}, evidence=(), reason_codes=conflicts)
    reasons = [field + '_missing' for field in ('attribution_model', 'attribution_window', 'conversion_definition', 'cost_definition')
               if not getattr(one, field)]
    for quality in {one.quality_status, two.quality_status} - {'complete'}:
        reasons.append('data_' + quality)
    context = two.model_copy(update={
        'period_start': one.period_start, 'as_of': max(one.as_of, two.as_of),
        'completeness': None if one.completeness is None or two.completeness is None else min(one.completeness, two.completeness),
        'quality_status': next(q for q in ('stale', 'partial', 'unknown', 'complete')
                               if q in {one.quality_status, two.quality_status}),
        'calculation_version': 'cpa_rca@1', 'sample_size': None})
    sources = tuple({source.id: source for source in (*before.sources, *after.sources)}.values())
    if len(sources) != len({(source.id, source.model_dump_json()) for source in (*before.sources, *after.sources)}):
        return RCAResult(status='incompatible', metrics={}, evidence=(), reason_codes=('source_revision_conflict',))
    refs = tuple(source.id for source in sources)
    metrics, evidence = {}, []
    for metric_id in ('cpa', 'cpc', 'cvr'):
        old, new = before.metrics[metric_id], after.metrics[metric_id]
        for suffix, unit, formula in (
                ('ratio', 'ratio', f'after.{metric_id} / before.{metric_id}'),
                ('change_abs', old.unit, f'after.{metric_id} - before.{metric_id}'),
                ('change_pct', 'pct', f'(after.{metric_id} - before.{metric_id}) / before.{metric_id} * 100')):
            missing = old.value is None or new.value is None
            zero_base = not missing and old.value <= 0 and suffix != 'change_abs'
            reason = 'missing_input' if missing else 'nonpositive_baseline' if zero_base else None
            value = (None if reason else new.value - old.value if suffix == 'change_abs'
                     else new.value / old.value if suffix == 'ratio' else (new.value - old.value) / old.value * 100)
            key = f'{metric_id}_{suffix}'
            output = _metric(context, key, value, unit, refs, reason)
            metrics[key] = output
            dependencies = tuple(e.id for r in (before, after) for e in r.evidence if e.claim_id == metric_id)
            evidence.append(_evidence(context, output, sources, formula, dependencies,
                                      limitations=('arithmetic_explanation_only', 'root_cause_not_established')))
            if reason:
                reasons.append(reason)
    return RCAResult(status='insufficient' if reasons else 'success', metrics=metrics, evidence=tuple(evidence),
                     reason_codes=tuple(sorted(set(reasons))),
                     hypotheses=('traffic_mix_change', 'conversion_lag', 'tracking_change',
                                 'competition_unverified', 'landing_page_unverified'))
