"""New P0 stays tenant-scoped, import-only and disabled until explicitly enabled."""
from uuid import uuid4
from decimal import Decimal

import pytest

from app.api.app import create_app
from test_api_support import client_for, cookie, session, settings, user
from test_schema import connected, new_workspace


PROFILE = {
    'name': 'Синтетический бизнес', 'industry_code': 'b2b', 'business_model': 'b2b',
    'products': ['Услуга'], 'geography': ['Москва'], 'currency': 'RUB', 'timezone': 'Europe/Moscow',
    'goal': 'Квалифицированные обращения', 'conversion_definition': 'qualified_lead',
    'average_order_value': None, 'gross_margin_pct': None, 'sales_cycle_days': 90,
    'budget_limit': None, 'seasonality': None, 'advantages': [], 'crm_available': False,
}


def payload(cost='10000', clicks='500', conversions='50', start='2026-10-01', end='2026-10-08'):
    return {'data_mode': 'synthetic', 'period_start': start, 'period_end': end, 'currency': 'RUB',
            'timezone': 'Europe/Moscow', 'attribution_model': 'last', 'attribution_window': '30d',
            'conversion_definition': 'qualified_lead', 'cost_definition': 'ad_cost_excluding_vat',
            'account_ids': [], 'values': {'cost': cost, 'clicks': clicks, 'conversions': conversions}}


@pytest.fixture
def intel(db, rw):
    owner = user(rw)
    ws = new_workspace(rw, user=owner)
    rw.execute('SELECT start_registration_trial(%s,%s)', (owner, ws))
    with client_for(create_app(settings(db, intelligence_enabled=True))) as client:
        client.owner_id = owner
        yield client, ws, {'Origin': 'https://app.example.test', **cookie(session(rw, owner))}


def route(ws, suffix=''):
    return f'/api/v1/workspaces/ws_{ws}/intelligence' + suffix


def test_disabled_is_server_enforced(db, rw):
    owner = user(rw)
    ws = new_workspace(rw, user=owner)
    headers = {'Origin': 'https://app.example.test', **cookie(session(rw, owner))}
    with client_for(create_app(settings(db))) as client:
        assert client.get(route(ws), headers=headers).json()['enabled'] is False
        assert client.post(route(ws, '/import'), headers=headers, json=payload()).status_code == 403


def test_profile_revision_and_provenance(intel):
    client, ws, headers = intel
    body = {'expected_revision': 0, 'fields': PROFILE}
    response = client.post(route(ws, '/profile'), headers=headers, json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['revision'] == 1
    assert result['provenance']['name']['origin'] == 'user_confirmed'
    assert result['provenance']['name']['actor_id'] > 0
    assert client.post(route(ws, '/profile'), headers=headers, json=body).status_code == 409
    assert client.get(route(ws), headers=headers).json()['profile']['fields']['sales_cycle_days'] == 90


@pytest.mark.parametrize('question', ['metrics', 'audiences'])
@pytest.mark.parametrize('baseline_scope', ['missing', 'local', 'foreign'])
def test_unused_baseline_is_rejected_before_creating_run(intel, rw, question, baseline_scope):
    client, ws, headers = intel
    client.post(route(ws, '/profile'), headers=headers, json={'expected_revision': 0, 'fields': PROFILE})
    imported = client.post(route(ws, '/import'), headers=headers, json=payload()).json()['id']
    baseline = str(uuid4())
    if baseline_scope == 'local':
        baseline = imported
    elif baseline_scope == 'foreign':
        other = new_workspace(rw, user=client.owner_id)
        baseline = client.post(route(other, '/import'), headers=headers, json=payload()).json()['id']
    response = client.post(route(ws, '/analyze'), headers=headers, json={
        'question': question, 'import_id': imported, 'before_import_id': baseline,
        'idempotency_key': str(uuid4()),
    })
    assert response.status_code == 400, response.text
    assert rw.execute('SELECT count(*) FROM intelligence_runs WHERE workspace_id=%s', (ws,)).fetchone()[0] == 0


@pytest.mark.parametrize('kind', ['profiles', 'imports', 'runs'])
@pytest.mark.parametrize('window', ['daily', 'history'])
def test_limits_are_workspace_scoped_and_allow_idempotent_retries(intel, rw, monkeypatch, kind, window):
    from app.api.intelligence import DAILY_LIMITS, HISTORY_LIMITS
    monkeypatch.setitem(DAILY_LIMITS if window == 'daily' else HISTORY_LIMITS, kind, 1)
    client, ws, headers = intel
    profile = {'expected_revision': 0, 'fields': PROFILE}
    assert client.post(route(ws, '/profile'), headers=headers, json=profile).status_code == 200
    if kind == 'profiles':
        response = client.post(route(ws, '/profile'), headers=headers, json={**profile, 'expected_revision': 1})
    else:
        imported = client.post(route(ws, '/import'), headers=headers, json=payload()).json()['id']
        if kind == 'imports':
            assert client.post(route(ws, '/import'), headers=headers, json=payload()).json()['id'] == imported
            response = client.post(route(ws, '/import'), headers=headers, json=payload('11000'))
        else:
            body = {'question': 'metrics', 'import_id': imported, 'idempotency_key': str(uuid4())}
            first = client.post(route(ws, '/analyze'), headers=headers, json=body)
            assert first.status_code == 200, first.text
            assert client.post(route(ws, '/analyze'), headers=headers, json=body).json()['id'] == first.json()['id']
            response = client.post(route(ws, '/analyze'), headers=headers,
                                   json={**body, 'idempotency_key': str(uuid4())})
    assert response.status_code == 429, response.text
    other = new_workspace(rw, user=client.owner_id)
    rw.execute("""INSERT INTO subscriptions(workspace_id,plan,status,price,current_period_start,current_period_end)
        VALUES(%s,'start','active',2990,now(),now()+interval '30 days')""", (other,))
    assert client.post(route(other, '/profile'), headers=headers, json=profile).status_code == 200
    imported = client.post(route(other, '/import'), headers=headers, json=payload())
    assert imported.status_code == 200, imported.text
    assert client.post(route(other, '/analyze'), headers=headers, json={
        'question': 'metrics', 'import_id': imported.json()['id'], 'idempotency_key': str(uuid4()),
    }).status_code == 200


def test_import_idempotency_scope_and_legal_gate(intel, rw):
    client, ws, headers = intel
    first = client.post(route(ws, '/import'), headers=headers, json=payload())
    assert first.status_code == 200, first.text
    assert client.post(route(ws, '/import'), headers=headers, json=payload()).json()['id'] == first.json()['id']
    assert client.post(route(ws, '/import'), headers=headers,
                       json={**payload(), 'data_mode': 'imported'}).status_code == 403
    assert client.post(route(ws, '/import'), headers=headers,
                       json={**payload(), 'values': {'cost': 12.34}}).status_code == 400
    foreign = new_workspace(rw, user=user(rw))
    assert client.get(route(foreign), headers=headers).status_code == 404


def test_rca_and_decision_are_durable_but_never_applied(intel):
    client, ws, headers = intel
    assert client.post(route(ws, '/profile'), headers=headers,
                       json={'expected_revision': 0, 'fields': PROFILE}).status_code == 200
    before = client.post(route(ws, '/import'), headers=headers, json=payload()).json()['id']
    after = client.post(route(ws, '/import'), headers=headers,
                        json=payload('12000', '400', '20', '2026-10-08', '2026-10-15')).json()['id']
    request = {'question': 'why_cpa', 'import_id': after, 'before_import_id': before,
               'idempotency_key': str(uuid4())}
    response = client.post(route(ws, '/analyze'), headers=headers, json=request)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run['result']['comparison']['root_cause'] == 'not_established'
    assert run['profile_revision'] == 1
    assert client.post(route(ws, '/analyze'), headers=headers, json=request).json()['id'] == run['id']
    rec = run['recommendations'][0]
    decision = {'run_id': run['id'], 'recommendation_id': rec['id'], 'revision': 1,
                'expected_state_version': 0, 'decision': 'approved', 'reason': 'Проверить гипотезу',
                'idempotency_key': str(uuid4())}
    accepted = client.post(route(ws, '/decisions'), headers=headers, json=decision)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['status'] == 'approved'
    assert client.post(route(ws, '/decisions'), headers=headers, json=decision).json() == accepted.json()
    assert client.post(route(ws, '/decisions'), headers=headers,
                       json={**decision, 'idempotency_key': str(uuid4())}).status_code == 409
    history = client.get(route(ws), headers=headers).json()['runs']
    assert history[0]['recommendations'][0]['status'] == 'approved'
    assert client.post(route(ws, '/analyze'), headers=headers,
                       json={**request, 'question': 'shell'}).status_code == 400


def test_viewer_cannot_change_profile_import_run_or_decision(intel, rw):
    client, ws, _ = intel
    viewer = user(rw)
    org = rw.execute('SELECT organization_id FROM workspaces WHERE id=%s', (ws,)).fetchone()[0]
    rw.execute("SELECT set_organization_member(%s,%s,%s,'member')", (client.owner_id, org, viewer))
    rw.execute("SELECT set_workspace_member(%s,%s,%s,'viewer')", (client.owner_id, ws, viewer))
    headers = {'Origin': 'https://app.example.test', **cookie(session(rw, viewer))}
    assert client.get(route(ws), headers=headers).json()['can_write'] is False
    bodies = {'/profile': {'expected_revision': 0, 'fields': PROFILE}, '/import': payload(),
              '/analyze': {'question': 'metrics', 'import_id': str(uuid4()), 'before_import_id': None,
                           'idempotency_key': str(uuid4())},
              '/decisions': {'run_id': str(uuid4()), 'recommendation_id': 'missing', 'revision': 1,
                             'expected_state_version': 0, 'decision': 'approved', 'reason': 'Проверить',
                             'idempotency_key': str(uuid4())}}
    for suffix, body in bodies.items():
        assert client.post(route(ws, suffix), headers=headers, json=body).status_code == 403


def test_foreign_import_cannot_be_used_and_idempotency_key_is_bound(intel, rw):
    client, ws, headers = intel
    client.post(route(ws, '/profile'), headers=headers, json={'expected_revision': 0, 'fields': PROFILE})
    imported = client.post(route(ws, '/import'), headers=headers, json=payload()).json()['id']
    request = {'question': 'metrics', 'import_id': imported, 'idempotency_key': str(uuid4())}
    first = client.post(route(ws, '/analyze'), headers=headers, json=request)
    assert first.status_code == 200, first.text
    assert client.post(route(ws, '/analyze'), headers=headers,
                       json={**request, 'question': 'audiences'}).status_code == 409
    owner = user(rw)
    foreign = new_workspace(rw, user=owner)
    rw.execute('SELECT start_registration_trial(%s,%s)', (owner, foreign))
    other_headers = {'Origin': 'https://app.example.test', **cookie(session(rw, owner))}
    client.post(route(foreign, '/profile'), headers=other_headers, json={'expected_revision': 0, 'fields': PROFILE})
    assert client.post(route(foreign, '/analyze'), headers=other_headers,
                       json={**request, 'idempotency_key': str(uuid4())}).status_code == 404
    assert client.get(route(foreign), headers=other_headers).json()['runs'] == []


def test_profile_edit_invalidates_pending_decision(intel):
    client, ws, headers = intel
    client.post(route(ws, '/profile'), headers=headers, json={'expected_revision': 0, 'fields': PROFILE})
    imported = client.post(route(ws, '/import'), headers=headers, json=payload()).json()['id']
    run = client.post(route(ws, '/analyze'), headers=headers,
                      json={'question': 'metrics', 'import_id': imported, 'idempotency_key': str(uuid4())}).json()
    client.post(route(ws, '/profile'), headers=headers,
                json={'expected_revision': 1, 'fields': {**PROFILE, 'goal': 'Новая цель'}})
    rec = run['recommendations'][0]
    response = client.post(route(ws, '/decisions'), headers=headers,
                           json={'run_id': run['id'], 'recommendation_id': rec['id'], 'revision': 1,
                                 'expected_state_version': 0, 'decision': 'approved', 'reason': 'Проверить',
                                 'idempotency_key': str(uuid4())})
    assert response.status_code == 409


def test_verifier_blocks_tampered_result_before_run_is_saved(intel, monkeypatch):
    from app.api import intelligence
    client, ws, headers = intel
    client.post(route(ws, '/profile'), headers=headers, json={'expected_revision': 0, 'fields': PROFILE})
    imported = client.post(route(ws, '/import'), headers=headers, json=payload()).json()['id']
    calculate = intelligence._calculate

    def wrong(*args, **kwargs):
        result = calculate(*args, **kwargs)
        result.metrics['cpa'] = result.metrics['cpa'].model_copy(update={'value': Decimal('1')})
        return result

    monkeypatch.setattr(intelligence, '_calculate', wrong)
    response = client.post(route(ws, '/analyze'), headers=headers,
                           json={'question': 'metrics', 'import_id': imported, 'idempotency_key': str(uuid4())})
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'verification_blocked'
    assert client.get(route(ws), headers=headers).json()['runs'] == []


@pytest.mark.parametrize('revoke', ['approval', 'account'])
def test_current_access_is_rechecked_for_history_replay_and_decisions(intel, rw, revoke):
    from dataclasses import replace
    client, ws, headers = intel
    client.app.state.settings = replace(client.app.state.settings, intelligence_real_data_approved=True)
    connection = connected(rw, 'direct', ws, 'synthetic-account')
    account = rw.execute('INSERT INTO direct_accounts(direct_connection_id,is_selected) VALUES(%s,true) RETURNING id',
                         (connection,)).fetchone()[0]
    client.post(route(ws, '/profile'), headers=headers, json={'expected_revision': 0, 'fields': PROFILE})
    imported = client.post(route(ws, '/import'), headers=headers,
                           json={**payload(), 'data_mode': 'imported', 'account_ids': [account]}).json()['id']
    request = {'question': 'metrics', 'import_id': imported, 'idempotency_key': str(uuid4())}
    run = client.post(route(ws, '/analyze'), headers=headers, json=request).json()
    decision = {'run_id': run['id'], 'recommendation_id': run['recommendations'][0]['id'], 'revision': 1,
                'expected_state_version': 0, 'decision': 'approved', 'reason': 'Проверить',
                'idempotency_key': str(uuid4())}
    assert client.post(route(ws, '/decisions'), headers=headers, json=decision).status_code == 200
    if revoke == 'approval':
        client.app.state.settings = replace(client.app.state.settings, intelligence_real_data_approved=False)
    else:
        rw.execute('UPDATE direct_accounts SET is_selected=false WHERE id=%s', (account,))
    overview = client.get(route(ws), headers=headers).json()
    assert overview['imports'] == [] and overview['runs'] == []
    assert client.post(route(ws, '/analyze'), headers=headers, json=request).status_code == 404
    assert client.post(route(ws, '/analyze'), headers=headers,
                       json={**request, 'idempotency_key': str(uuid4())}).status_code == 404
    assert client.post(route(ws, '/decisions'), headers=headers, json=decision).status_code == 404
    assert client.get(route(ws, '/imports/' + imported), headers=headers).status_code == 404


def test_history_pages_are_bounded_and_do_not_repeat_runs(intel, rw):
    client, ws, headers = intel
    client.post(route(ws, '/profile'), headers=headers, json={'expected_revision': 0, 'fields': PROFILE})
    imported = client.post(route(ws, '/import'), headers=headers, json=payload()).json()['id']
    identities = set()
    for _ in range(7):
        response = client.post(route(ws, '/analyze'), headers=headers,
                               json={'question': 'metrics', 'import_id': imported, 'idempotency_key': str(uuid4())})
        assert response.status_code == 200, response.text
        identities.add(response.json()['id'])
    first = client.get(route(ws), headers=headers).json()
    assert len(first['runs']) == 5 and first['next_cursor'] == first['runs'][-1]['id']
    second = client.get(route(ws) + '?cursor=' + first['next_cursor'], headers=headers).json()
    assert len(second['runs']) == 2 and second['next_cursor'] is None
    assert {r['id'] for r in first['runs']} | {r['id'] for r in second['runs']} == identities
    assert not ({r['id'] for r in first['runs']} & {r['id'] for r in second['runs']})
    assert client.get(route(ws) + '?cursor=not-a-uuid', headers=headers).status_code == 400
    foreign = new_workspace(rw, user=user(rw))
    assert client.get(route(foreign) + '?cursor=' + first['next_cursor'], headers=headers).status_code == 404


def test_revoked_candidates_do_not_hide_older_allowed_history_or_imports(intel, rw):
    from dataclasses import replace
    from psycopg.types.json import Jsonb
    client, ws, headers = intel
    client.post(route(ws, '/profile'), headers=headers, json={'expected_revision': 0, 'fields': PROFILE})
    imported = client.post(route(ws, '/import'), headers=headers, json=payload()).json()['id']
    allowed = client.post(route(ws, '/analyze'), headers=headers,
                          json={'question': 'metrics', 'import_id': imported, 'idempotency_key': str(uuid4())}).json()
    client.app.state.settings = replace(client.app.state.settings, intelligence_real_data_approved=True)
    connection = connected(rw, 'direct', ws, 'revoked-history')
    account = rw.execute('INSERT INTO direct_accounts(direct_connection_id,is_selected) VALUES(%s,true) RETURNING id',
                         (connection,)).fetchone()[0]
    for index in range(50):
        response = client.post(route(ws, '/import'), headers=headers,
                               json={**payload(cost=str(11000 + index)), 'data_mode': 'imported', 'account_ids': [account]})
        assert response.status_code == 200, response.text
    blocked_import = response.json()['id']
    blocked = client.post(route(ws, '/analyze'), headers=headers,
                          json={'question': 'metrics', 'import_id': blocked_import, 'idempotency_key': str(uuid4())}).json()
    for _ in range(50):
        identity = uuid4()
        clone = {**blocked, 'id': str(identity)}
        rw.execute('''INSERT INTO intelligence_runs(id,workspace_id,import_id,profile_revision,idempotency_key,
            request_hash,payload,created_by) VALUES(%s,%s,%s,1,%s,%s,%s,%s)''',
            (identity, ws, blocked_import, uuid4(), 'a' * 64, Jsonb(clone), client.owner_id))
    client.app.state.settings = replace(client.app.state.settings, intelligence_real_data_approved=False)
    page = client.get(route(ws), headers=headers).json()
    assert [run['id'] for run in page['runs']] == [allowed['id']]
    assert [item['id'] for item in page['imports']] == [imported]
    assert page['next_cursor'] is None


def test_insufficient_or_incompatible_analysis_does_not_publish_a_recommendation(intel):
    client, ws, headers = intel
    client.post(route(ws, '/profile'), headers=headers, json={'expected_revision': 0, 'fields': PROFILE})
    empty = client.post(route(ws, '/import'), headers=headers,
                         json={**payload(), 'values': {'cost': None}}).json()['id']
    result = client.post(route(ws, '/analyze'), headers=headers,
                          json={'question': 'metrics', 'import_id': empty, 'idempotency_key': str(uuid4())}).json()
    assert result['recommendations'] == []
    assert result['result']['missing_inputs']
    before = client.post(route(ws, '/import'), headers=headers, json=payload()).json()['id']
    after = client.post(route(ws, '/import'), headers=headers,
                        json={**payload('12000', '400', '20', '2026-10-08', '2026-10-15'),
                              'attribution_model': 'different_attribution'}).json()['id']
    result = client.post(route(ws, '/analyze'), headers=headers,
                          json={'question': 'why_cpa', 'import_id': after, 'before_import_id': before,
                                'idempotency_key': str(uuid4())}).json()
    assert result['recommendations'] == []
    assert result['result']['comparison']['status'] == 'incompatible'


def test_import_evidence_resolves_exact_source_and_rechecks_workspace(intel, rw):
    client, ws, headers = intel
    body = payload()
    imported = client.post(route(ws, '/import'), headers=headers, json=body).json()['id']
    response = client.get(route(ws, '/imports/' + imported), headers=headers)
    assert response.status_code == 200
    assert response.json()['id'] == imported
    assert response.json()['data'] == body
    assert 'no-store' in response.headers['cache-control']
    foreign = new_workspace(rw, user=user(rw))
    assert client.get(route(foreign, '/imports/' + imported), headers=headers).status_code == 404


@pytest.mark.parametrize('metric_id', ['cost', 'roas', 'gross_profit', 'contribution_after_ads', 'cpa_sale'])
def test_verifier_checks_trusted_inputs_and_all_financial_outputs(metric_id):
    from app.api.intelligence import _verify
    from app.api.errors import ApiError
    from app.intelligence.contracts import AnalysisResult
    from app.intelligence.economics import calculate_metrics
    from test_intelligence_economics import setup_case
    context, source = setup_case()
    values = {'cost': '12000', 'clicks': '600', 'conversions': '60', 'sales': '12',
              'attributed_revenue': '60000', 'net_revenue': '60000', 'cogs': '30000', 'other_variable_costs': '0'}
    result = calculate_metrics(context, values, (source,))
    data = result.model_dump()
    data['metrics'][metric_id]['value'] = Decimal('999')
    for proof in data['evidence']:
        if proof['claim_id'] == metric_id:
            proof['output']['value'] = Decimal('999')
    tampered = AnalysisResult.model_validate(data)
    with pytest.raises(ApiError) as error:
        _verify(tampered, values)
    assert error.value.code == 'verification_blocked'


def test_comparison_verifier_rejects_consistent_tampering_of_output_and_evidence():
    from datetime import date
    from app.api.intelligence import _verify_comparison
    from app.api.errors import ApiError
    from app.intelligence.contracts import RCAResult
    from app.intelligence.economics import compare_cpa
    from test_intelligence_economics import calculate
    before = calculate({'cost': 10000, 'clicks': 500, 'conversions': 50}, source_id='before')
    after = calculate({'cost': 12000, 'clicks': 400, 'conversions': 20}, start=date(2026, 10, 8), source_id='after')
    data = compare_cpa(before, after).model_dump()
    data['metrics']['cpa_ratio']['value'] = Decimal('9')
    for proof in data['evidence']:
        if proof['claim_id'] == 'cpa_ratio':
            proof['output']['value'] = Decimal('9')
    with pytest.raises(ApiError) as error:
        _verify_comparison(RCAResult.model_validate(data), before, after)
    assert error.value.code == 'verification_blocked'
