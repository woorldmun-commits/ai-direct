"""The local allowlist rejects untrusted authority and invalid contracts before execution."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.intelligence import tools
from test_intelligence_economics import calculate, setup_case


def context(**changes):
    fields = dict(actor_id=7, workspace_id=1, allowed_accounts=frozenset({1}),
                  request_id='request-1', run_id='run-1',
                  deadline=datetime.now(timezone.utc) + timedelta(seconds=60),
                  permissions=frozenset({'metrics.read', 'analysis.run'}))
    return tools.ToolContext(**(fields | changes))


def payload(**changes):
    analysis, source = setup_case()
    fields = dict(context=analysis, values={'cost': '100', 'clicks': '10', 'conversions': '2'}, sources=(source,))
    return fields | changes


def invoke(body=None, **kwargs):
    return tools.invoke('metrics.calculate', payload() if body is None else body,
                        context=kwargs.pop('context', context()),
                        budget=kwargs.pop('budget', tools.RunBudget()), **kwargs)


def test_fixed_registry_exposes_contracts_and_returns_typed_local_result():
    definitions = tools.definitions()
    assert {tool.tool_id for tool in definitions} == {'metrics.calculate', 'cpa.compare', 'audience.discover'}
    for tool in definitions:
        assert tool.input_schema['type'] == 'object' and tool.output_schema['type'] == 'object'
        assert tool.side_effects == 'read_only' and tool.timeout_ms > 0 and tool.max_cost == 0
        assert tool.retry_policy == {'max_retries': 0}
        assert tool.validation_rules and tool.error_codes and tool.test_refs
    budget = tools.RunBudget()
    result = invoke(budget=budget)
    assert result.status == 'success' and result.error is None
    assert result.data.metrics['cpa'].value == Decimal('50')
    assert result.evidence_refs and result.cost == 0 and budget.calls == 1
    assert result.trace[0].tool_id == 'metrics.calculate'
    assert set(result.trace[0].model_dump()) == {'tool_id', 'tool_version', 'status', 'elapsed_ms', 'error_code'}


@pytest.mark.parametrize('patch,reason', [
    ({'tool_id': 'shell'}, 'unknown_tool'),
    ({'version': '999'}, 'unsupported_version'),
    ({'requested_side_effects': 'external_write'}, 'side_effects_forbidden'),
    ({'context': lambda: context(permissions=frozenset())}, 'forbidden_permission'),
    ({'context': lambda: context(workspace_id=2)}, 'forbidden_scope'),
    ({'context': lambda: context(allowed_accounts=frozenset())}, 'forbidden_scope'),
    ({'context': lambda: context(deadline=datetime.now(timezone.utc) - timedelta(seconds=1))}, 'deadline_exceeded'),
    ({'budget': tools.RunBudget(max_calls=0)}, 'call_limit_exceeded'),
])
def test_rejections_happen_before_handler(monkeypatch, patch, reason):
    # Start deadlines at execution; collecting the full suite can take over a minute.
    if 'context' in patch:
        patch = patch | {'context': patch['context']()}
    calls = []
    monkeypatch.setattr(tools, '_HANDLERS', {'metrics.calculate': lambda body: calls.append(body)})
    options = dict(tool_id='metrics.calculate', context=context(), budget=tools.RunBudget()) | patch
    result = tools.invoke(options.pop('tool_id'), payload(), **options)
    assert result.status == 'error' and result.data is None and result.error.code == reason
    assert calls == []


@pytest.mark.parametrize('bad', [
    {'context': 'not-a-context'},
    payload(values={'cost': 1.5}),
    payload(values={'cost': True}),
    payload(values={'cost': 'NaN'}),
    payload(values={'unknown_metric': '1'}),
    payload() | {'tenant_id': 999},
])
def test_invalid_input_cannot_reach_handler(monkeypatch, bad):
    calls = []
    monkeypatch.setattr(tools, '_HANDLERS', {'metrics.calculate': lambda body: calls.append(body)})
    result = invoke(bad)
    assert result.error.code == 'invalid_input' and calls == []


def test_foreign_source_and_comparison_are_denied_before_handler(monkeypatch):
    _, source = setup_case()
    source = source.model_copy(update={'workspace_id': 2})
    calls = []
    monkeypatch.setattr(tools, '_HANDLERS', {'metrics.calculate': lambda body: calls.append(body),
                                         'cpa.compare': lambda body: calls.append(body)})
    assert invoke(payload(sources=(source,))).error.code == 'forbidden_scope'
    first = calculate({'cost': 100, 'clicks': 10, 'conversions': 2})
    second = calculate({'cost': 100, 'clicks': 10, 'conversions': 2}, workspace_id=2)
    result = tools.invoke('cpa.compare', {'before': first, 'after': second}, context=context(), budget=tools.RunBudget())
    assert result.error.code == 'forbidden_scope' and not calls


def test_wrong_output_or_missing_evidence_is_not_success(monkeypatch):
    monkeypatch.setattr(tools, '_HANDLERS', {'metrics.calculate': lambda _: {'metrics': {}}})
    result = invoke()
    assert result.error.code == 'invalid_output' and result.data is None
    calculated = calculate({'cost': 100, 'clicks': 10, 'conversions': 2})
    raw = calculated.model_dump()
    raw['evidence'] = []
    monkeypatch.setattr(tools, '_HANDLERS', {'metrics.calculate': lambda _: raw})
    assert invoke().error.code == 'invalid_output'


def test_another_allowed_dataset_is_not_the_requested_output(monkeypatch):
    alternative = calculate({'cost': 100, 'clicks': 10, 'conversions': 2}, source_id='different-source')
    monkeypatch.setattr(tools, '_HANDLERS', {'metrics.calculate': lambda _: alternative})
    assert invoke().error.code == 'invalid_output'


def test_missing_required_metric_and_changed_observation_are_invalid_output(monkeypatch):
    result = calculate({'cost': 100, 'clicks': 10, 'conversions': 2})
    raw = result.model_dump()
    del raw['metrics']['cpa']
    raw['evidence'] = [item for item in raw['evidence'] if item['claim_id'] != 'cpa']
    monkeypatch.setattr(tools, '_HANDLERS', {'metrics.calculate': lambda _: raw})
    assert invoke().error.code == 'invalid_output'
    changed = calculate({'cost': 999, 'clicks': 10, 'conversions': 2})
    monkeypatch.setattr(tools, '_HANDLERS', {'metrics.calculate': lambda _: changed})
    assert invoke().error.code == 'invalid_output'


def test_algorithm_version_is_not_selected_by_input(monkeypatch):
    analysis, _ = setup_case()
    calls = []
    monkeypatch.setattr(tools, '_HANDLERS', {'metrics.calculate': lambda body: calls.append(body)})
    result = invoke(payload(context=analysis.model_copy(update={'calculation_version': 'economics@99'})))
    assert result.error.code == 'unsupported_version' and not calls


def test_success_requires_typed_data_and_error_requires_failure():
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match='tool_status_data'):
        tools.ToolResult(status='success', data=None, elapsed_ms=0, tool_version='1', trace=())
    with pytest.raises(ValidationError, match='tool_status_error'):
        tools.ToolResult(status='error', data=None, elapsed_ms=0, tool_version='1', trace=())


def test_local_handler_failure_is_safe_and_does_not_echo_input(monkeypatch):
    def fails(_):
        raise RuntimeError('synthetic-private-source-do-not-echo')
    monkeypatch.setattr(tools, '_HANDLERS', {'metrics.calculate': fails})
    result = invoke()
    assert result.error.code == 'tool_failed'
    assert 'synthetic-private-source-do-not-echo' not in result.model_dump_json()


def test_per_run_budget_is_atomic_and_exhaustion_does_not_call_handler(monkeypatch):
    budget = tools.RunBudget(max_calls=1)
    calculated = calculate({'cost': 100, 'clicks': 10, 'conversions': 2})
    calls = []
    def handler(body):
        calls.append(body)
        return calculated
    monkeypatch.setattr(tools, '_HANDLERS', {'metrics.calculate': handler})
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: invoke(budget=budget), range(4)))
    assert sum(result.error is None for result in results) == 1
    assert len(calls) == budget.calls == 1


def test_cost_budget_overrun_is_rejected_before_handler(monkeypatch):
    budget = tools.RunBudget(max_cost=Decimal('0'))
    budget.cost = Decimal('1')
    monkeypatch.setattr(tools, '_HANDLERS', {'metrics.calculate': lambda _: pytest.fail('called')})
    assert invoke(budget=budget).error.code == 'cost_limit_exceeded'


def test_deadline_crossed_during_local_handler_discards_output(monkeypatch):
    start = datetime.now(timezone.utc)
    clock = iter((start, start + timedelta(seconds=3)))
    monkeypatch.setattr(tools, '_now', lambda: next(clock))
    result = invoke(context=context(deadline=start + timedelta(seconds=2)))
    assert result.error.code == 'deadline_exceeded' and result.data is None


def test_tool_timeout_discards_local_result(monkeypatch):
    from dataclasses import replace
    definition = next(item for item in tools.definitions() if item.tool_id == 'metrics.calculate')
    monkeypatch.setattr(tools, '_TOOLS', {'metrics.calculate': replace(definition, timeout_ms=0)})
    result = invoke()
    assert result.error.code == 'tool_timeout' and result.data is None


@pytest.mark.parametrize('options', [{'max_calls': True}, {'max_calls': 9}, {'max_calls': -1},
                                    {'max_cost': -1}, {'max_cost': 1.5}])
def test_run_limits_cannot_expand_policy_or_lose_decimal_precision(options):
    with pytest.raises(ValueError):
        tools.RunBudget(**options)


def test_unknown_tool_does_not_echo_untrusted_content():
    result = tools.invoke('https://private.example/secret', payload(), context=context(), budget=tools.RunBudget())
    assert result.error.code == 'unknown_tool' and 'private.example' not in result.model_dump_json()


def test_comparison_returns_arithmetic_evidence_and_preserves_insufficiency():
    before = calculate({'cost': '10000', 'clicks': '500', 'conversions': '50'}, source_id='before')
    after = calculate({'cost': '12000', 'clicks': '400', 'conversions': '20'},
                      start=before.context.period_end, source_id='after')
    result = tools.invoke('cpa.compare', {'before': before, 'after': after}, context=context(), budget=tools.RunBudget())
    assert result.status == 'success' and result.data.root_cause == 'not_established'
    assert result.data.metrics['cpa_ratio'].value == 3
    assert result.evidence_refs
    unavailable = invoke(payload(values={'cost': None}))
    assert unavailable.status == 'insufficient' and unavailable.error is None
    assert unavailable.missing_inputs and unavailable.data.metrics['cpa'].value is None
