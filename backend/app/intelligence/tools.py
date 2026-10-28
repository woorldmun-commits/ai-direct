"""Fixed local tools: server authority and typed evidence stay outside user/model content."""
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from threading import Lock
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator

from app.intelligence.contracts import (
    AnalysisContext, AnalysisResult, PositiveInt, RCAResult, SourceReference, StrictModel, decimal_number,
)
from app.intelligence.economics import INPUT_UNITS, RATIOS, calculate_metrics, compare_cpa
from app.intelligence.knowledge import discover_audiences, industries
from app.intelligence.profiles import BusinessProfile, Short, Text


class ToolContext(StrictModel):
    actor_id: PositiveInt
    workspace_id: PositiveInt
    allowed_accounts: frozenset[PositiveInt]
    request_id: Annotated[str, Field(min_length=1, max_length=200)]
    run_id: Annotated[str, Field(min_length=1, max_length=200)]
    deadline: datetime
    permissions: frozenset[Annotated[str, Field(min_length=1, max_length=64)]]
    privacy_policy_version: Annotated[str, Field(min_length=1, max_length=100)] = 'local@1'

    @field_validator('deadline')
    @classmethod
    def aware_deadline(cls, value):
        return AnalysisContext.aware(value)


@dataclass
class RunBudget:
    max_calls: int = 8
    max_cost: Decimal = Decimal('0')
    calls: int = field(default=0, init=False)
    cost: Decimal = field(default=Decimal('0'), init=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self):
        self.max_cost = decimal_number(self.max_cost)
        if (type(self.max_calls) is not int or not 0 <= self.max_calls <= 8
                or self.max_cost is None or self.max_cost < 0):
            raise ValueError('invalid_run_budget')


class MetricCalculationInput(StrictModel):
    context: AnalysisContext
    values: dict[str, Decimal | None]
    sources: Annotated[tuple[SourceReference, ...], Field(max_length=100)]

    @field_validator('values', mode='before')
    @classmethod
    def strict_values(cls, values):
        if not isinstance(values, dict) or set(values) - INPUT_UNITS.keys():
            raise ValueError('metric_allowlist')
        return {key: decimal_number(value) for key, value in values.items()}


class CPAComparisonInput(StrictModel):
    before: AnalysisResult
    after: AnalysisResult


class AudienceDiscoveryInput(StrictModel):
    workspace_id: PositiveInt
    profile: BusinessProfile


class KnowledgeSource(StrictModel):
    title: Text
    url: Annotated[str, Field(min_length=1, max_length=2000, pattern=r'^https://')]


class AudienceSegment(StrictModel):
    id: Short
    name: Short
    intent: Text
    status: Literal['hypothesis']
    profile_revision: PositiveInt
    needs: tuple[Short, ...]
    objections: tuple[Text, ...]
    channels: tuple[Short, ...]
    geography: tuple[Short, ...]
    source_refs: tuple[KnowledgeSource, ...]
    missing_inputs: tuple[Text, ...]
    test_plan: Text
    success_metric: Short


class AudienceDiscoveryResult(StrictModel):
    workspace_id: PositiveInt
    profile_revision: PositiveInt
    segments: tuple[AudienceSegment, ...]
    limitations: tuple[Text, ...]


class ToolFailure(StrictModel):
    code: str
    retryable: Literal[False] = False


class ToolTrace(StrictModel):
    tool_id: str
    tool_version: str
    status: Literal['success', 'partial', 'insufficient', 'unavailable', 'error']
    elapsed_ms: Annotated[StrictInt, Field(ge=0)]
    error_code: str | None = None


class ToolResult(StrictModel):
    status: Literal['success', 'partial', 'insufficient', 'unavailable', 'error']
    data: AnalysisResult | RCAResult | AudienceDiscoveryResult | None
    evidence_refs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    error: ToolFailure | None = None
    elapsed_ms: Annotated[StrictInt, Field(ge=0)]
    cost: Decimal = Decimal('0')
    tool_version: str
    trace: tuple[ToolTrace, ...]

    @model_validator(mode='after')
    def result_state(self):
        if (self.status == 'error') != (self.error is not None):
            raise ValueError('tool_status_error_mismatch')
        if (self.status == 'error') != (self.data is None):
            raise ValueError('tool_status_data_mismatch')
        return self


@dataclass(frozen=True)
class ToolDefinition:
    tool_id: str
    purpose: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    algorithm_version: str
    required_permissions: tuple[str, ...] = ('metrics.read', 'analysis.run')
    data_scope: str = 'current_workspace_and_allowed_accounts'
    schema_version: str = '1'
    side_effects: Literal['read_only'] = 'read_only'
    timeout_ms: int = 2000
    max_cost: Decimal = Decimal('0')
    max_calls: int = 8
    validation_rules: tuple[str, ...] = ('input_schema', 'current_scope', 'output_schema', 'resolved_evidence')
    error_codes: tuple[str, ...] = (
        'unknown_tool', 'unsupported_version', 'side_effects_forbidden', 'forbidden_permission',
        'forbidden_scope', 'invalid_input', 'invalid_output', 'deadline_exceeded', 'call_limit_exceeded',
        'cost_limit_exceeded', 'tool_timeout', 'tool_failed',
    )
    test_refs: tuple[str, ...] = ('tests/test_intelligence_tools.py',)

    @property
    def input_schema(self):
        return self.input_model.model_json_schema()

    @property
    def output_schema(self):
        return self.output_model.model_json_schema()

    @property
    def retry_policy(self):
        return {'max_retries': 0}


_TOOLS = MappingProxyType({
    'metrics.calculate': ToolDefinition('metrics.calculate', 'Calculate scoped Decimal metrics and evidence',
                                       MetricCalculationInput, AnalysisResult, 'economics@1'),
    'cpa.compare': ToolDefinition('cpa.compare', 'Compare CPA arithmetically without claiming root cause',
                                 CPAComparisonInput, RCAResult, 'cpa_rca@1'),
    'audience.discover': ToolDefinition('audience.discover', 'Propose testable audience hypotheses from a versioned profile',
                                       AudienceDiscoveryInput, AudienceDiscoveryResult, 'audience_discovery@1'),
})
_HANDLERS = MappingProxyType({
    'metrics.calculate': lambda body: calculate_metrics(body.context, body.values, body.sources),
    'cpa.compare': lambda body: compare_cpa(body.before, body.after),
    'audience.discover': lambda body: AudienceDiscoveryResult(
        workspace_id=body.workspace_id, profile_revision=body.profile.revision,
        **discover_audiences(body.profile.model_dump(mode='json'))),
})


def definitions() -> tuple[ToolDefinition, ...]:
    return tuple(_TOOLS.values())


def _now():
    return datetime.now(timezone.utc)


def _authorize_scope(body, context):
    if isinstance(body, AudienceDiscoveryInput):
        return body.workspace_id == context.workspace_id
    analyses = (body.context,) if isinstance(body, MetricCalculationInput) else (body.before.context, body.after.context)
    sources = body.sources if isinstance(body, MetricCalculationInput) else (*body.before.sources, *body.after.sources)
    for item in (*analyses, *sources):
        if item.workspace_id != context.workspace_id or not set(item.account_ids) <= context.allowed_accounts:
            return False
    return True


def _output_scope(data, body, context):
    if isinstance(data, AudienceDiscoveryResult):
        profile = body.profile
        known = next((item for item in industries() if item['code'] == profile.fields.industry_code), None)
        urls = {item['url'] for item in known['sources']} if known else set()
        return (data.workspace_id == context.workspace_id and data.profile_revision == profile.revision
                and all(segment.profile_revision == profile.revision and segment.status == 'hypothesis'
                        and segment.success_metric == profile.fields.conversion_definition
                        and segment.needs == tuple(profile.fields.products)
                        and segment.geography == tuple(profile.fields.geography)
                        and {source.url for source in segment.source_refs} == urls for segment in data.segments))
    if isinstance(data, AnalysisResult):
        expected = set(INPUT_UNITS) | {item[0] for item in RATIOS} | {'gross_profit', 'contribution_after_ads'}
        if data.metrics.keys() != expected:
            return False
        if any(data.metrics[key].value != body.values.get(key) for key in INPUT_UNITS):
            return False
        if data.sources != body.sources:
            return False
        fields = ('workspace_id', 'account_ids', 'currency', 'period_start', 'period_end', 'timezone', 'as_of',
                  'attribution_model', 'attribution_window', 'conversion_definition', 'cost_definition',
                  'calculation_version', 'completeness', 'sample_size')
        if any(getattr(data.context, key) != getattr(body.context, key) for key in fields):
            return False
        return _authorize_scope(MetricCalculationInput(context=data.context, values={}, sources=data.sources), context)
    sources = {source.id for source in (*body.before.sources, *body.after.sources)}
    if data.status == 'incompatible':
        return not data.metrics and not data.evidence and bool(data.reason_codes)
    expected = {f'{key}_{suffix}' for key in ('cpa', 'cpc', 'cvr') for suffix in ('ratio', 'change_abs', 'change_pct')}
    if data.metrics.keys() != expected:
        return False
    evidence = {item.claim_id: item for item in data.evidence}
    if len(evidence) != len(data.evidence) or evidence.keys() != data.metrics.keys():
        return False
    return all(evidence[key].workspace_id == context.workspace_id and evidence[key].output == metric
               and metric.metric_id == key and set(metric.source_refs) == sources
               for key, metric in data.metrics.items())


def invoke(tool_id: str, payload, *, context: ToolContext, budget: RunBudget, version: str = '1',
           requested_side_effects: str = 'read_only') -> ToolResult:
    """No user-supplied registry or authority. Calls reserve the shared run budget atomically."""
    started = time.perf_counter()
    now = _now()
    definition = _TOOLS.get(tool_id)

    def finish(code=None, data=None, status='error', warnings=(), missing=()):
        elapsed = max(0, int((time.perf_counter() - started) * 1000))
        schema_version = definition.schema_version if definition else '1'
        evidence_refs = (tuple(sorted({source.url for segment in data.segments for source in segment.source_refs}))
                         if isinstance(data, AudienceDiscoveryResult) else tuple(item.id for item in data.evidence) if data else ())
        return ToolResult(status=status, data=data, error=ToolFailure(code=code) if code else None,
                          evidence_refs=evidence_refs,
                          warnings=warnings, missing_inputs=missing, elapsed_ms=elapsed,
                          cost=Decimal('0'), tool_version=schema_version,
                          trace=(ToolTrace(tool_id=definition.tool_id if definition else 'unknown',
                                           tool_version=schema_version, status=status, elapsed_ms=elapsed, error_code=code),))

    if definition is None:
        return finish('unknown_tool')
    if version != definition.schema_version:
        return finish('unsupported_version')
    if requested_side_effects != definition.side_effects:
        return finish('side_effects_forbidden')
    if not set(definition.required_permissions) <= context.permissions:
        return finish('forbidden_permission')
    if now >= context.deadline:
        return finish('deadline_exceeded')
    try:
        body = definition.input_model.model_validate(payload.model_dump() if isinstance(payload, BaseModel) else payload)
    except (TypeError, ValueError):
        return finish('invalid_input')
    if not _authorize_scope(body, context):
        return finish('forbidden_scope')
    if isinstance(body, MetricCalculationInput) and body.context.calculation_version != definition.algorithm_version:
        return finish('unsupported_version')
    with budget._lock:
        if budget.calls >= budget.max_calls:
            return finish('call_limit_exceeded')
        if budget.cost + definition.max_cost > budget.max_cost:
            return finish('cost_limit_exceeded')
        budget.calls += 1
        budget.cost += definition.max_cost
    try:
        raw = _HANDLERS[definition.tool_id](body)
    except (TypeError, ValueError):
        return finish('invalid_input')
    except Exception:
        return finish('tool_failed')
    # shortcut: bounded pure local handlers cannot be interrupted; use cancellable jobs before adding long/network tools.
    if _now() >= context.deadline:
        return finish('deadline_exceeded')
    if (time.perf_counter() - started) * 1000 > definition.timeout_ms:
        return finish('tool_timeout')
    try:
        data = definition.output_model.model_validate(raw.model_dump() if isinstance(raw, BaseModel) else raw)
        if not _output_scope(data, body, context):
            return finish('invalid_output')
    except (TypeError, ValueError, AttributeError):
        return finish('invalid_output')
    if isinstance(data, RCAResult):
        return finish(data=data, status='success' if data.status == 'success' else 'insufficient',
                      warnings=data.reason_codes, missing=data.reason_codes)
    if isinstance(data, AudienceDiscoveryResult):
        return finish(data=data, status='success', warnings=data.limitations,
                      missing=tuple(sorted({item for segment in data.segments for item in segment.missing_inputs})))
    missing = tuple(key for key in INPUT_UNITS if data.metrics.get(key) is None or data.metrics[key].value is None)
    available = any(metric.value is not None for metric in data.metrics.values())
    return finish(data=data, status='insufficient' if not available else 'partial' if data.warnings else 'success',
                  warnings=data.warnings, missing=missing)
