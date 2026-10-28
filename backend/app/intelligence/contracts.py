"""Additive P0 contracts. Legacy Value and inclusive Window retain their original meaning."""
import re
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.contract import Value

PositiveInt = Annotated[StrictInt, Field(gt=0)]
Quality = Literal['complete', 'partial', 'stale', 'unknown']
ClaimKind = Literal['observed_fact', 'derived_fact', 'industry_knowledge', 'hypothesis', 'forecast', 'unavailable']
Status = Literal['actual', 'estimated', 'unavailable', 'insufficient']


def decimal_number(raw):
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (Decimal, int, str)):
        raise ValueError('decimal_required')
    text = format(raw, 'f') if isinstance(raw, Decimal) and raw.is_finite() else str(raw)
    if not re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?', text):
        raise ValueError('decimal_required')
    return Decimal(text)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Period(StrictModel):
    period_start: date
    period_end: date

    @field_validator('period_start', 'period_end', mode='before')
    @classmethod
    def day(cls, raw):
        if type(raw) is date:
            return raw
        if isinstance(raw, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', raw):
            return date.fromisoformat(raw)
        raise ValueError('date_required')

    @model_validator(mode='after')
    def interval(self):
        if self.period_start >= self.period_end:
            raise ValueError('half_open_period_required')
        return self


class AnalysisContext(Period):
    workspace_id: PositiveInt
    account_ids: tuple[PositiveInt, ...] = ()
    currency: str
    timezone: str
    as_of: datetime
    attribution_model: str | None = None
    attribution_window: str | None = None
    conversion_definition: str | None = None
    cost_definition: str | None = None
    quality_status: Quality = 'unknown'
    completeness: Decimal | None = None
    sample_size: Annotated[StrictInt, Field(ge=0)] | None = None
    calculation_version: str = 'economics@1'

    @field_validator('account_ids')
    @classmethod
    def accounts(cls, raw):
        if tuple(sorted(set(raw))) != raw:
            raise ValueError('account_scope_must_be_sorted_unique')
        return raw

    @field_validator('currency')
    @classmethod
    def currency_code(cls, raw):
        if not re.fullmatch(r'[A-Z]{3}', raw):
            raise ValueError('currency_code_required')
        return raw

    @field_validator('timezone')
    @classmethod
    def time_zone(cls, raw):
        try:
            ZoneInfo(raw)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError('invalid_timezone') from None
        return raw

    @field_validator('as_of')
    @classmethod
    def aware(cls, raw):
        if raw.tzinfo is None or raw.utcoffset() is None:
            raise ValueError('timezone_required')
        return raw

    @field_validator('completeness', mode='before')
    @classmethod
    def completeness_number(cls, raw):
        value = decimal_number(raw)
        if value is not None and not 0 <= value <= 1:
            raise ValueError('completeness_bounds')
        return value

    @field_validator('calculation_version')
    @classmethod
    def version(cls, raw):
        if not re.fullmatch(r'[a-z0-9_]+@[1-9][0-9]*', raw):
            raise ValueError('calculation_version_required')
        return raw


class SourceReference(Period):
    id: Annotated[str, Field(min_length=1, max_length=200)]
    workspace_id: PositiveInt
    provider: Annotated[str, Field(min_length=1)]
    source_kind: Literal['live_read', 'import', 'synthetic', 'user_input']
    fetched_at: datetime
    currency: str
    account_ids: tuple[PositiveInt, ...] = ()
    attribution_model: str | None = None
    attribution_window: str | None = None
    conversion_definition: str | None = None
    cost_definition: str | None = None
    processing_version: str = 'source@1'
    connector_id: str | None = None
    import_id: str | None = None
    filters: dict[str, str] = Field(default_factory=dict)
    quality_status: Quality = 'unknown'
    raw_record_refs: tuple[str, ...] = ()

    @field_validator('fetched_at')
    @classmethod
    def aware(cls, raw):
        return AnalysisContext.aware(raw)

    @field_validator('currency')
    @classmethod
    def currency_code(cls, raw):
        return AnalysisContext.currency_code(raw)

    @field_validator('account_ids')
    @classmethod
    def accounts(cls, raw):
        return AnalysisContext.accounts(raw)


def validate_sources(context: AnalysisContext, sources: Sequence[SourceReference]) -> None:
    if len({s.id for s in sources}) != len(sources):
        raise ValueError('duplicate_source_reference')
    for source in sources:
        if source.workspace_id != context.workspace_id:
            raise ValueError('incompatible_workspace')
        if source.account_ids != context.account_ids:
            raise ValueError('incompatible_accounts')
        if source.currency != context.currency:
            raise ValueError('incompatible_currency')
        if not source.period_start <= context.period_start < context.period_end <= source.period_end:
            raise ValueError('incompatible_source_period')
        if source.fetched_at > context.as_of:
            raise ValueError('source_after_as_of')
        for field in ('attribution_model', 'attribution_window', 'conversion_definition', 'cost_definition'):
            if getattr(source, field) != getattr(context, field):
                raise ValueError('incompatible_' + field)


class MetricValue(Period):
    metric_id: Annotated[str, Field(min_length=1)]
    value: Decimal | None
    unit: Literal['money', 'count', 'pct', 'ratio']
    currency: str | None
    status: Status
    reason_code: str | None = None
    source_refs: tuple[str, ...] = ()
    timezone: str
    as_of: datetime
    completeness: Decimal | None = None
    sample_size: Annotated[StrictInt, Field(ge=0)] | None = None
    attribution_model: str | None = None
    attribution_window: str | None = None
    conversion_definition: str | None = None
    cost_definition: str | None = None
    calculation_version: str
    quality_status: Quality

    @field_validator('value', mode='before')
    @classmethod
    def numeric(cls, raw):
        return decimal_number(raw)

    @field_validator('as_of')
    @classmethod
    def aware(cls, raw):
        return AnalysisContext.aware(raw)

    @field_validator('timezone')
    @classmethod
    def time_zone(cls, raw):
        return AnalysisContext.time_zone(raw)

    @field_validator('completeness', mode='before')
    @classmethod
    def completeness_number(cls, raw):
        return AnalysisContext.completeness_number(raw)

    @model_validator(mode='after')
    def availability(self):
        absent = self.status in ('unavailable', 'insufficient')
        if absent != (self.value is None) or absent != bool(self.reason_code):
            raise ValueError('status_value_reason_mismatch')
        if not absent and not self.source_refs:
            raise ValueError('source_reference_required')
        if (self.unit == 'money') != (self.currency is not None):
            raise ValueError('currency_unit_mismatch')
        if self.currency is not None:
            AnalysisContext.currency_code(self.currency)
        AnalysisContext.version(self.calculation_version)
        return self


class Evidence(Period):
    id: str
    workspace_id: PositiveInt
    claim_id: str
    kind: ClaimKind
    source_refs: tuple[str, ...]
    input_ids: tuple[str, ...]
    metric_refs: tuple[str, ...]
    formula: str | None
    algorithm_version: str
    generated_at: datetime
    timezone: str
    quality_status: Quality
    limitations: tuple[str, ...] = ()
    verifier_result: Literal['not_checked', 'pass', 'warning', 'block'] = 'not_checked'
    output: MetricValue

    @field_validator('generated_at')
    @classmethod
    def aware(cls, raw):
        return AnalysisContext.aware(raw)

    @model_validator(mode='after')
    def provenance(self):
        if (self.kind == 'unavailable') != (self.output.value is None):
            raise ValueError('claim_availability_mismatch')
        if self.kind == 'derived_fact' and (not self.formula or not self.metric_refs):
            raise ValueError('calculation_provenance_required')
        if self.kind in ('observed_fact', 'derived_fact') and (not self.source_refs or not self.input_ids):
            raise ValueError('source_provenance_required')
        if (self.generated_at, self.algorithm_version, self.quality_status) != (
                self.output.as_of, self.output.calculation_version, self.output.quality_status):
            raise ValueError('claim_metadata_mismatch')
        if self.output.metric_id != self.claim_id or self.output.source_refs != self.source_refs:
            raise ValueError('claim_output_mismatch')
        if (self.period_start, self.period_end, self.timezone) != (
                self.output.period_start, self.output.period_end, self.output.timezone):
            raise ValueError('claim_period_mismatch')
        return self


class AnalysisResult(StrictModel):
    context: AnalysisContext
    sources: tuple[SourceReference, ...]
    metrics: dict[str, MetricValue]
    evidence: tuple[Evidence, ...]
    warnings: tuple[str, ...] = ()

    @model_validator(mode='after')
    def resolved_evidence(self):
        validate_sources(self.context, self.sources)
        sources = {source.id for source in self.sources}
        if len(sources) != len(self.sources) or any(s.workspace_id != self.context.workspace_id for s in self.sources):
            raise ValueError('invalid_source_scope')
        records = {item.claim_id: item for item in self.evidence}
        if len(records) != len(self.evidence) or records.keys() != self.metrics.keys():
            raise ValueError('metric_evidence_coverage')
        if len({item.id for item in self.evidence}) != len(self.evidence):
            raise ValueError('duplicate_evidence_id')
        for key, metric in self.metrics.items():
            evidence = records[key]
            if evidence.workspace_id != self.context.workspace_id or evidence.output != metric or metric.metric_id != key:
                raise ValueError('metric_evidence_mismatch')
            if not set(metric.source_refs) <= sources:
                raise ValueError('unresolved_source_reference')
            if metric.unit == 'money' and metric.currency != self.context.currency:
                raise ValueError('metric_currency_mismatch')
            for field in ('period_start', 'period_end', 'timezone', 'as_of', 'attribution_model', 'attribution_window',
                          'conversion_definition', 'cost_definition', 'quality_status', 'calculation_version'):
                if getattr(metric, field) != getattr(self.context, field):
                    raise ValueError('metric_context_mismatch')
        return self


class RCAResult(StrictModel):
    status: Literal['success', 'insufficient', 'incompatible']
    metrics: dict[str, MetricValue]
    evidence: tuple[Evidence, ...]
    reason_codes: tuple[str, ...] = ()
    root_cause: Literal['not_established'] = 'not_established'
    hypotheses: tuple[str, ...] = ()


def legacy_to_metric(value: Value, *, metric_id: str, context: AnalysisContext,
                     source_refs: tuple[str, ...]) -> MetricValue:
    end = value.period_to + timedelta(days=1)
    if (value.period_from, end) != (context.period_start, context.period_end):
        raise ValueError('legacy_period_mismatch')
    if value.unit == 'rub' and context.currency != 'RUB':
        raise ValueError('incompatible_currency')
    return MetricValue(
        metric_id=metric_id, value=value.amount, unit={'rub': 'money', 'count': 'count', 'pct': 'pct'}[value.unit],
        currency='RUB' if value.unit == 'rub' else None, status=value.calculation_type,
        reason_code=value.unavailable_reason, source_refs=source_refs, period_start=value.period_from, period_end=end,
        timezone=context.timezone, as_of=context.as_of, completeness=context.completeness,
        sample_size=context.sample_size, attribution_model=context.attribution_model,
        attribution_window=context.attribution_window, conversion_definition=context.conversion_definition,
        cost_definition=context.cost_definition,
        calculation_version=context.calculation_version,
        quality_status='partial' if value.data_status == 'partial' else context.quality_status)
