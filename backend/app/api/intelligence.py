"""Import-only P0 in the existing workspace boundary; no LLM, arbitrary tools or ad writes."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

from app.api.deps import Conn, CurrentWorkspace
from app.api.errors import ApiError, not_found
from app.intelligence.contracts import AnalysisContext, AnalysisResult, Period, SourceReference, decimal_number
from app.intelligence.economics import INPUT_UNITS
from app.intelligence.knowledge import industries
from app.intelligence.profiles import BusinessFields
from app.intelligence.tools import AudienceDiscoveryInput, CPAComparisonInput, MetricCalculationInput, RunBudget, ToolContext, invoke

router = APIRouter()
Text = Annotated[StrictStr, Field(min_length=1, max_length=500)]
Short = Annotated[StrictStr, Field(min_length=1, max_length=100)]
NonnegativeInt = Annotated[StrictInt, Field(ge=0)]


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ProfileUpdate(Body):
    expected_revision: NonnegativeInt
    fields: BusinessFields


class Import(Period):
    data_mode: Literal['synthetic', 'imported']
    currency: Literal['RUB']
    timezone: Literal['Europe/Moscow']
    attribution_model: Short
    attribution_window: Short
    conversion_definition: Short
    cost_definition: Short
    account_ids: Annotated[tuple[Annotated[StrictInt, Field(gt=0)], ...], Field(max_length=100)] = ()
    values: dict[str, Decimal | None]

    @field_validator('values', mode='before')
    @classmethod
    def values_format(cls, raw):
        if not isinstance(raw, dict) or not raw or set(raw) - INPUT_UNITS.keys():
            raise ValueError('metric_allowlist')
        result = {}
        for key, value in raw.items():
            number = decimal_number(value)
            if number is not None and (abs(number) > Decimal('999999999999') or number.as_tuple().exponent < -8):
                raise ValueError('metric_bounds')
            result[key] = number
        return result

    @field_validator('period_end')
    @classmethod
    def date_bound(cls, value, info):
        start = info.data.get('period_start')
        if start is not None and (value - start).days > 366:
            raise ValueError('period_bounds')
        return value


class AnalysisRequest(Body):
    question: Literal['why_cpa', 'metrics', 'audiences']
    import_id: UUID
    before_import_id: UUID | None = None
    idempotency_key: UUID


class Decision(Body):
    run_id: UUID
    recommendation_id: Short
    revision: Literal[1]
    expected_state_version: NonnegativeInt
    decision: Literal['approved', 'postponed', 'rejected', 'cancelled']
    reason: Text
    idempotency_key: UUID


def _enabled(request, *, write=False, ws=None):
    if not request.app.state.settings.intelligence_enabled:
        raise ApiError(403, 'feature_disabled', message='Аналитический сценарий пока выключен.')
    if write and ws.role not in ('owner', 'admin', 'approver', 'analyst'):
        raise ApiError(403, 'forbidden_role')


def _hash(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _lock(conn, ws):
    conn.execute('SELECT pg_advisory_xact_lock(%s)', (ws.id,))


def _profile(conn, ws):
    row = conn.execute('SELECT payload FROM intelligence_profiles WHERE workspace_id=%s ORDER BY revision DESC LIMIT 1',
                       (ws.id,)).fetchone()
    return row[0] if row else None


def _import_access_sql(alias):
    # alias is an internal SQL identifier, never request content.
    return f'''({alias}.data_mode='synthetic' OR %s)
        AND ({alias}.data_mode='synthetic' OR jsonb_array_length({alias}.payload->'account_ids')>0)
        AND NOT EXISTS (
          SELECT 1 FROM jsonb_array_elements_text({alias}.payload->'account_ids') requested(id)
          WHERE NOT EXISTS (
            SELECT 1 FROM direct_accounts a JOIN direct_connections c ON c.id=a.direct_connection_id
            WHERE a.id=requested.id::bigint AND a.is_selected AND c.workspace_id={alias}.workspace_id))'''


def _can_access_import(data, request, conn, ws):
    return conn.execute('SELECT ' + _import_access_sql('i') +
                        ' FROM (SELECT %s::jsonb AS payload,%s::text AS data_mode,%s::bigint AS workspace_id) i',
                        (request.app.state.settings.intelligence_real_data_approved,
                         Jsonb(data), data['data_mode'], ws.id)).fetchone()[0]


def _import(conn, ws, identity, request):
    row = conn.execute('SELECT payload,created_at FROM intelligence_imports WHERE workspace_id=%s AND id=%s',
                       (ws.id, identity)).fetchone()
    if row is None or not _can_access_import(row[0], request, conn, ws):
        raise not_found()
    return row


def _can_access_run(run, request, conn, ws):
    row = conn.execute('SELECT import_id,before_import_id FROM intelligence_runs WHERE workspace_id=%s AND id=%s',
                       (ws.id, run['id'])).fetchone()
    if row is None:
        return False
    for identity in row:
        if identity is not None:
            try:
                _import(conn, ws, identity, request)
            except ApiError:
                return False
    return True


def _tool_context(request, conn, ws, identity):
    accounts = conn.execute('''SELECT a.id FROM direct_accounts a JOIN direct_connections c ON c.id=a.direct_connection_id
        WHERE c.workspace_id=%s AND a.is_selected''', (ws.id,)).fetchall()
    return ToolContext(actor_id=ws.actor.user_id, workspace_id=ws.id,
                       allowed_accounts=frozenset(row[0] for row in accounts),
                       request_id=request.state.request_id, run_id=str(identity),
                       deadline=datetime.now(timezone.utc) + timedelta(seconds=60),
                       permissions=frozenset({'metrics.read', 'analysis.run'}))


def _invoke(tool_id, payload, context, budget, trace):
    result = invoke(tool_id, payload, context=context, budget=budget)
    trace.extend(entry.model_dump(mode='json') for entry in result.trace)
    if result.error:
        status = 403 if result.error.code in ('forbidden_scope', 'forbidden_permission', 'side_effects_forbidden') else 409
        raise ApiError(status, 'analysis_unavailable', result.error.code,
                       message='Расчёт не завершён. Проверьте доступ, данные и ограничения анализа.')
    return result.data


def _calculate(body, created_at, identity, ws, *, context, budget, trace):
    quality = 'complete' if body['data_mode'] == 'synthetic' else 'unknown'
    data_context = AnalysisContext(workspace_id=ws.id, account_ids=tuple(body['account_ids']), currency=body['currency'],
                              period_start=body['period_start'], period_end=body['period_end'], timezone=body['timezone'],
                              as_of=created_at, attribution_model=body['attribution_model'],
                              attribution_window=body['attribution_window'], conversion_definition=body['conversion_definition'],
                              cost_definition=body['cost_definition'], quality_status=quality,
                              completeness='1' if body['data_mode'] == 'synthetic' else None)
    source = SourceReference(id=f'import:{identity}', workspace_id=ws.id, account_ids=data_context.account_ids,
                             provider='user_input', source_kind='synthetic' if body['data_mode'] == 'synthetic' else 'import',
                             fetched_at=created_at, period_start=data_context.period_start, period_end=data_context.period_end,
                             currency=data_context.currency, attribution_model=data_context.attribution_model,
                             attribution_window=data_context.attribution_window, conversion_definition=data_context.conversion_definition,
                             cost_definition=body['cost_definition'], import_id=str(identity), quality_status=quality,
                             raw_record_refs=(f'import:{identity}:aggregate',))
    return _invoke('metrics.calculate', MetricCalculationInput(context=data_context, values=body['values'], sources=(source,)),
                   context, budget, trace)


def _verify(result, inputs):
    """Resolve evidence and recompute financial outputs against the stored input record."""
    try:
        result = AnalysisResult.model_validate(result.model_dump())
    except ValueError:
        raise ApiError(409, 'verification_blocked', message='Доказательства результата требуют проверки.') from None
    refs = {source.id for source in result.sources}
    evidence = {entry.claim_id: entry for entry in result.evidence}
    expected = {key: decimal_number(inputs.get(key)) for key in INPUT_UNITS}
    revenue, cogs = expected['net_revenue'], expected['cogs']
    expected['gross_profit'] = revenue - cogs if revenue is not None and cogs is not None else None
    profit, variable, cost = expected['gross_profit'], expected['other_variable_costs'], expected['cost']
    expected['contribution_after_ads'] = profit - variable - cost if all(v is not None for v in (profit, variable, cost)) else None
    formulas = {'gross_profit': 'net_revenue - cogs',
                'contribution_after_ads': 'net_revenue - cogs - other_variable_costs - cost'}
    for key, numerator, denominator, scale in (
            ('cpa', 'cost', 'conversions', 1), ('cpc', 'cost', 'clicks', 1),
            ('cvr', 'conversions', 'clicks', 100), ('ctr', 'clicks', 'impressions', 100),
            ('cpl', 'cost', 'leads', 1), ('cpql', 'cost', 'qualified_leads', 1),
            ('cpa_sale', 'cost', 'sales', 1), ('paid_cac', 'cost', 'new_customers', 1),
            ('roas', 'attributed_revenue', 'cost', 1), ('drr', 'cost', 'attributed_revenue', 100),
            ('gross_margin', 'gross_profit', 'net_revenue', 100)):
        n, d = expected[numerator], expected[denominator]
        expected[key] = n / d * scale if n is not None and d is not None and d > 0 else None
        formulas[key] = f'{numerator} / {denominator}' + (' * 100' if scale == 100 else '')
    if set(result.metrics) != set(expected):
        raise ApiError(409, 'verification_blocked', message='Набор проверяемых показателей не совпадает.')
    for key, metric in result.metrics.items():
        proof = evidence.get(key)
        if (proof is None or proof.workspace_id != result.context.workspace_id or proof.output != metric
                or not set(metric.source_refs) <= refs or key != metric.metric_id
                or metric.value != expected[key] or (key in formulas and proof.formula != formulas[key])):
            raise ApiError(409, 'verification_blocked', message='Доказательства результата требуют проверки.')
    return {'status': 'pass', 'version': 'runtime_financial@1',
            'limitations': ['Проверены ссылки и финансовые формулы относительно импорта; полнота источника и причинный эффект этим не доказаны.']}


def _verify_comparison(comparison, before, after):
    if comparison.status == 'incompatible':
        if comparison.metrics or comparison.evidence or not comparison.reason_codes:
            raise ApiError(409, 'verification_blocked')
        return
    proofs = {entry.claim_id: entry for entry in comparison.evidence}
    expected_keys = {f'{metric}_{suffix}' for metric in ('cpa', 'cpc', 'cvr')
                     for suffix in ('ratio', 'change_abs', 'change_pct')}
    if set(comparison.metrics) != expected_keys or set(proofs) != expected_keys or len(proofs) != len(comparison.evidence):
        raise ApiError(409, 'verification_blocked')
    context = after.context
    refs = {source.id for result in (before, after) for source in result.sources}
    for metric_id in ('cpa', 'cpc', 'cvr'):
        old, new = before.metrics[metric_id], after.metrics[metric_id]
        known = old.value is not None and new.value is not None
        for suffix in ('ratio', 'change_abs', 'change_pct'):
            key = f'{metric_id}_{suffix}'
            metric, proof = comparison.metrics[key], proofs[key]
            value = None
            if known and (suffix == 'change_abs' or old.value > 0):
                value = new.value - old.value if suffix == 'change_abs' else (
                    new.value / old.value if suffix == 'ratio' else (new.value - old.value) / old.value * 100)
            unit = old.unit if suffix == 'change_abs' else 'ratio' if suffix == 'ratio' else 'pct'
            if (metric.value != value or metric.unit != unit
                    or metric.currency != (context.currency if unit == 'money' else None)
                    or (metric.period_start, metric.period_end, metric.timezone) != (
                        before.context.period_start, context.period_end, context.timezone)
                    or proof.workspace_id != context.workspace_id or proof.output != metric
                    or set(metric.source_refs) != refs):
                raise ApiError(409, 'verification_blocked', message='Разбор изменения не прошёл независимую проверку.')


def _decorate(conn, ws, run):
    latest = conn.execute('''SELECT DISTINCT ON (recommendation_id) recommendation_id,status,state_version
        FROM intelligence_decisions WHERE workspace_id=%s AND run_id=%s
        ORDER BY recommendation_id,state_version DESC''', (ws.id, run['id'])).fetchall()
    decisions = {key: (status, version) for key, status, version in latest}
    return {**run, 'recommendations': [{**rec, **dict(zip(('status', 'state_version'), decisions[rec['id']]))}
                                      if rec['id'] in decisions else rec for rec in run['recommendations']]}


@router.get('/workspaces/{workspace_id}/intelligence')
def overview(request: Request, conn: Conn, ws: CurrentWorkspace, cursor: UUID | None = None):
    settings = request.app.state.settings
    empty = {'enabled': settings.intelligence_enabled,
             'mode': 'import_only' if settings.intelligence_real_data_approved else 'synthetic',
             'can_write': ws.role in ('owner', 'admin', 'approver', 'analyst'),
             'profile': None, 'industries': [], 'imports': [], 'runs': [], 'next_cursor': None,
             'limits': {'external_llm': False, 'external_execution': False, 'max_tool_calls': 8}}
    if not settings.intelligence_enabled:
        return empty
    approved = settings.intelligence_real_data_approved
    imports = conn.execute('''SELECT i.id,i.data_mode,i.created_at,i.payload->>'period_start',i.payload->>'period_end',i.payload
        FROM intelligence_imports i WHERE i.workspace_id=%s AND ''' + _import_access_sql('i') +
        ' ORDER BY i.created_at DESC,i.id LIMIT 50', (ws.id, approved)).fetchall()
    params = (ws.id, approved, approved)
    condition = ''
    if cursor:
        last = conn.execute('SELECT payload,created_at FROM intelligence_runs WHERE workspace_id=%s AND id=%s',
                            (ws.id, cursor)).fetchone()
        if last is None or not _can_access_run(last[0], request, conn, ws):
            raise not_found()
        condition = ' AND (r.created_at,r.id)<(%s,%s)'
        params += (last[1], cursor)
    runs = conn.execute('''SELECT r.payload FROM intelligence_runs r
        JOIN intelligence_imports i ON i.workspace_id=r.workspace_id AND i.id=r.import_id
        LEFT JOIN intelligence_imports b ON b.workspace_id=r.workspace_id AND b.id=r.before_import_id
        WHERE r.workspace_id=%s AND ''' + _import_access_sql('i') +
        ' AND (r.before_import_id IS NULL OR (' + _import_access_sql('b') + '))' + condition +
        ' ORDER BY r.created_at DESC,r.id LIMIT 6', params).fetchall()
    visible = [row[0] for row in runs if _can_access_run(row[0], request, conn, ws)]
    page = visible[:5]
    return {**empty, 'profile': _profile(conn, ws), 'industries': industries(),
            'imports': [dict(zip(('id', 'data_mode', 'created_at', 'period_start', 'period_end'), row[:5])) for row in imports
                        if _can_access_import(row[5], request, conn, ws)],
            'runs': [_decorate(conn, ws, run) for run in page],
            'next_cursor': page[-1]['id'] if len(visible) > 5 else None}


@router.post('/workspaces/{workspace_id}/intelligence/profile')
def update_profile(body: ProfileUpdate, request: Request, conn: Conn, ws: CurrentWorkspace):
    _enabled(request, write=True, ws=ws)
    _lock(conn, ws)
    previous = _profile(conn, ws)
    revision = previous['revision'] if previous else 0
    if body.expected_revision != revision:
        raise ApiError(409, 'stale_revision', message='Профиль изменился. Обновите страницу.')
    fields = body.fields.model_dump(mode='json')
    now = datetime.now(timezone.utc).isoformat()
    provenance = {key: previous['provenance'][key] if previous and previous['fields'].get(key) == value else
                  {'origin': 'user_confirmed', 'actor_id': ws.actor.user_id, 'updated_at': now}
                  for key, value in fields.items()}
    result = {'revision': revision + 1, 'fields': fields, 'provenance': provenance}
    conn.execute('INSERT INTO intelligence_profiles(workspace_id,revision,payload,created_by) VALUES(%s,%s,%s,%s)',
                 (ws.id, result['revision'], Jsonb(result), ws.actor.user_id))
    return result


@router.get('/workspaces/{workspace_id}/intelligence/imports/{import_id}')
def import_evidence(import_id: UUID, request: Request, conn: Conn, ws: CurrentWorkspace):
    _enabled(request)
    payload, created_at = _import(conn, ws, import_id, request)
    return {'id': import_id, 'created_at': created_at, 'source_kind': payload['data_mode'], 'data': payload}


@router.post('/workspaces/{workspace_id}/intelligence/import')
def import_data(body: Import, request: Request, conn: Conn, ws: CurrentWorkspace):
    _enabled(request, write=True, ws=ws)
    if body.data_mode == 'imported' and not request.app.state.settings.intelligence_real_data_approved:
        raise ApiError(403, 'feature_disabled', message='Импорт реальных данных требует отдельного допуска.')
    if body.account_ids:
        accounts = conn.execute('''SELECT a.id FROM direct_accounts a JOIN direct_connections c ON c.id=a.direct_connection_id
            WHERE c.workspace_id=%s AND a.is_selected AND a.id=ANY(%s) ORDER BY a.id''', (ws.id, list(body.account_ids))).fetchall()
        if tuple(row[0] for row in accounts) != body.account_ids:
            raise ApiError(403, 'forbidden_role')
    elif body.data_mode == 'imported':
        raise ApiError(400, 'invalid_request', 'account_scope_required')
    payload = body.model_dump(mode='json')
    identity, now = uuid4(), datetime.now(timezone.utc)
    try:
        _verify(_calculate(payload, now, identity, ws, context=_tool_context(request, conn, ws, identity),
                           budget=RunBudget(), trace=[]), payload['values'])
    except ValueError:
        raise ApiError(400, 'invalid_request', 'incompatible_data') from None
    fingerprint = _hash(payload)
    row = conn.execute('''INSERT INTO intelligence_imports(id,workspace_id,fingerprint,data_mode,payload,created_by)
        VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT (workspace_id,fingerprint) DO NOTHING RETURNING id,created_at''',
        (identity, ws.id, fingerprint, body.data_mode, Jsonb(payload), ws.actor.user_id)).fetchone()
    if row is None:
        row = conn.execute('SELECT id,created_at FROM intelligence_imports WHERE workspace_id=%s AND fingerprint=%s',
                           (ws.id, fingerprint)).fetchone()
    return {'id': row[0], 'created_at': row[1], 'data_mode': body.data_mode,
            'period_start': body.period_start, 'period_end': body.period_end}


@router.post('/workspaces/{workspace_id}/intelligence/analyze')
def analyze(body: AnalysisRequest, request: Request, conn: Conn, ws: CurrentWorkspace):
    _enabled(request, write=True, ws=ws)
    _lock(conn, ws)
    digest = _hash(body.model_dump(mode='json'))
    previous = conn.execute('SELECT request_hash,payload FROM intelligence_runs WHERE workspace_id=%s AND idempotency_key=%s',
                            (ws.id, body.idempotency_key)).fetchone()
    if previous:
        if not _can_access_run(previous[1], request, conn, ws):
            raise not_found()
        if previous[0] != digest:
            raise ApiError(409, 'idempotency_conflict')
        return _decorate(conn, ws, previous[1])
    profile = _profile(conn, ws)
    if profile is None:
        raise ApiError(409, 'profile_required', message='Сначала сохраните профиль бизнеса.')
    data, created_at = _import(conn, ws, body.import_id, request)
    if data['conversion_definition'] != profile['fields']['conversion_definition']:
        raise ApiError(409, 'profile_scope_changed', message='Определения конверсии профиля и импорта различаются.')
    identity = str(uuid4())
    context, budget, trace = _tool_context(request, conn, ws, identity), RunBudget(), []
    after = _calculate(data, created_at, body.import_id, ws, context=context, budget=budget, trace=trace)
    verification = _verify(after, data['values'])
    result, status = after.model_dump(mode='json'), 'completed'
    result['missing_inputs'] = [key for key in INPUT_UNITS if after.metrics[key].value is None]
    publish_recommendation = any(metric.value is not None for key, metric in after.metrics.items() if key not in INPUT_UNITS)
    title = 'Проверить определения и доступные метрики'
    if body.question == 'why_cpa':
        if body.before_import_id is None:
            raise ApiError(400, 'invalid_request', 'baseline_required')
        before_data, before_at = _import(conn, ws, body.before_import_id, request)
        if before_data['data_mode'] != data['data_mode']:
            raise ApiError(409, 'incompatible_data', 'different_data_modes')
        before = _calculate(before_data, before_at, body.before_import_id, ws, context=context, budget=budget, trace=trace)
        _verify(before, before_data['values'])
        comparison = _invoke('cpa.compare', CPAComparisonInput(before=before, after=after), context, budget, trace)
        _verify_comparison(comparison, before, after)
        result = {'before': before.model_dump(mode='json'), 'after': result,
                  'comparison': comparison.model_dump(mode='json')}
        status = 'completed' if comparison.status == 'success' else 'partial'
        publish_recommendation = comparison.status == 'success'
        title = 'Проверить гипотезы изменения CPA'
    elif body.question == 'audiences':
        audiences = _invoke('audience.discover', AudienceDiscoveryInput(workspace_id=ws.id, profile=profile),
                            context, budget, trace)
        result = audiences.model_dump(mode='json')
        publish_recommendation = bool(result['segments'])
        title = 'Спланировать проверку аудитории'
    recommendation = {'id': f'{identity}:1', 'revision': 1, 'state_version': 0, 'status': 'requires_decision',
                      'title': title, 'facts': ['Профиль и источники сохранены в указанной версии.'],
                      'hypotheses': ['Причина изменения и эффективность аудитории требуют отдельной проверки.'],
                      'risks': ['Синтетические данные не описывают реальную рекламу.' if data['data_mode'] == 'synthetic'
                                else 'Полнота и зрелость исходных данных не подтверждены.'],
                      'next_step': 'Проверить доказательства и выбрать внутреннее решение; рекламные действия не выполняются.'}
    run = {'id': identity, 'status': status, 'question': body.question, 'result': result,
           'profile_revision': profile['revision'], 'data_mode': data['data_mode'], 'verification': verification,
           'recommendations': [recommendation] if publish_recommendation else [],
           'created_at': datetime.now(timezone.utc).isoformat(),
           'trace': trace,
           'limits': {'external_llm': False, 'external_execution': False, 'max_tool_calls': budget.max_calls,
                      'tool_calls': budget.calls, 'deadline': context.deadline.isoformat()}}
    conn.execute('''INSERT INTO intelligence_runs(id,workspace_id,import_id,before_import_id,profile_revision,
        idempotency_key,request_hash,payload,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
        (UUID(identity), ws.id, body.import_id, body.before_import_id, profile['revision'], body.idempotency_key,
         digest, Jsonb(run), ws.actor.user_id))
    return run


@router.post('/workspaces/{workspace_id}/intelligence/decisions')
def decide(body: Decision, request: Request, conn: Conn, ws: CurrentWorkspace):
    _enabled(request, write=True, ws=ws)
    _lock(conn, ws)
    digest = _hash(body.model_dump(mode='json'))
    existing = conn.execute('SELECT request_hash,status,state_version FROM intelligence_decisions WHERE workspace_id=%s AND idempotency_key=%s',
                            (ws.id, body.idempotency_key)).fetchone()
    if existing:
        run = conn.execute('SELECT payload FROM intelligence_runs WHERE workspace_id=%s AND id=%s',
                           (ws.id, body.run_id)).fetchone()
        if run is None or not _can_access_run(run[0], request, conn, ws):
            raise not_found()
        if existing[0] != digest:
            raise ApiError(409, 'idempotency_conflict')
        return {'decision': existing[1], 'status': existing[1], 'state_version': existing[2]}
    row = conn.execute('SELECT payload FROM intelligence_runs WHERE workspace_id=%s AND id=%s', (ws.id, body.run_id)).fetchone()
    if row is None or not _can_access_run(row[0], request, conn, ws):
        raise not_found()
    run = _decorate(conn, ws, row[0])
    rec = next((r for r in run['recommendations'] if r['id'] == body.recommendation_id), None)
    if rec is None:
        raise not_found()
    if (_profile(conn, ws)['revision'] != run['profile_revision'] or rec['revision'] != body.revision
            or rec['state_version'] != body.expected_state_version
            or rec['status'] != 'requires_decision'):
        raise ApiError(409, 'stale_revision', message='Решение или профиль изменились. Нужна новая проверка.')
    version = rec['state_version'] + 1
    conn.execute('''INSERT INTO intelligence_decisions(workspace_id,run_id,recommendation_id,revision,state_version,
        status,reason,actor_id,idempotency_key,request_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
        (ws.id, body.run_id, body.recommendation_id, body.revision, version, body.decision, body.reason,
         ws.actor.user_id, body.idempotency_key, digest))
    return {'decision': body.decision, 'status': body.decision, 'state_version': version}
