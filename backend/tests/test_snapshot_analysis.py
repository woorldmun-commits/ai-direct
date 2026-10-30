from dataclasses import replace
from decimal import Decimal

from app.intelligence.contracts import AnalysisResult
from test_campaign_stats import funded, insights_api, req  # noqa: F401
from test_schema import chain  # noqa: F401
from test_api_support import user
from test_lifecycle import sync


def start_trial_on_data(rw,funded):
    rw.execute('SELECT start_registration_trial(%s,%s)', (funded['user'], funded['ws']))
    sync(rw,funded['ws'],funded['account'],funded['release'],100)


def test_snapshot_analysis_is_gated_and_scoped(insights_api, rw, funded, monkeypatch):
    path = 'intelligence/snapshot-analysis?days=7'
    assert req(insights_api, rw, funded, path).json() == {'available': False, 'reason': 'real_data_approval_required'}
    insights_api.app.state.settings = replace(insights_api.app.state.settings, intelligence_enabled=True,
                                            intelligence_real_data_approved=True)
    assert req(insights_api, rw, funded, path).status_code == 403
    start_trial_on_data(rw,funded)
    from datetime import datetime, timedelta
    from app.api import intelligence
    started = rw.execute('SELECT started_at FROM workspace_trial(%s)', (funded['ws'],)).fetchone()[0]
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return started+timedelta(minutes=1)
    monkeypatch.setattr(intelligence, 'datetime', Clock)
    response = req(insights_api, rw, funded, path)
    assert response.status_code == 200, response.text
    body = response.json()
    result = AnalysisResult.model_validate(body['result'])
    assert result.metrics['cost'].value == Decimal('700')
    assert result.metrics['conversions'].value == Decimal('7')
    assert result.metrics['cpa'].value == Decimal('100')
    assert result.context.account_ids == (funded['account'],)
    assert result.sources[0].source_kind == 'live_read'
    assert result.sources[0].raw_record_refs
    assert body['limits'] == {'external_llm': False, 'external_execution': False}
    assert req(insights_api, rw, funded, path, actor=user(rw)).status_code == 404
    rw.execute('UPDATE direct_accounts SET is_selected=false WHERE id=%s', (funded['account'],))
    assert req(insights_api, rw, funded, path).json() == {'available': False, 'reason': 'no_snapshot'}


def test_snapshot_quality_preserves_missing_values_and_staleness(insights_api, rw, funded, monkeypatch):
    from copy import deepcopy
    from datetime import datetime, timedelta, timezone
    from app.api import intelligence
    insights_api.app.state.settings = replace(insights_api.app.state.settings, intelligence_enabled=True,
                                            intelligence_real_data_approved=True)
    start_trial_on_data(rw,funded)
    data = intelligence.campaign_stats.build(rw, funded['ws'], intelligence.today_msk(), datetime.now(timezone.utc), days=7)
    data = deepcopy(data)
    for metric in data['summary'].values():
        metric['data_status'] = 'complete'
    for key in ('conversions', 'cpa'):
        data['summary'][key]['amount'] = None
    monkeypatch.setattr(intelligence.campaign_stats, 'build', lambda *args, **kwargs: data)
    # Freeze a recent period so missing conversions, rather than age, determines quality.
    monkeypatch.setattr(intelligence, 'today_msk', lambda: datetime.fromisoformat(data['period']['to']).date())
    path = 'intelligence/snapshot-analysis?days=7'
    result = req(insights_api, rw, funded, path).json()['result']
    assert result['context']['quality_status'] == 'partial'
    assert result['metrics']['conversions']['value'] is None and result['metrics']['cpa']['value'] is None
    data['provenance'][0]['sealed_at'] = (datetime.now(timezone.utc)-timedelta(days=5)).isoformat()
    result = req(insights_api, rw, funded, path).json()['result']
    assert result['context']['quality_status'] == 'stale'


def test_snapshot_sealed_during_request_precedes_result_as_of(insights_api, rw, funded, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.api import intelligence
    insights_api.app.state.settings = replace(insights_api.app.state.settings, intelligence_enabled=True,
                                            intelligence_real_data_approved=True)
    start_trial_on_data(rw,funded)
    now = datetime.now(timezone.utc)+timedelta(minutes=1)
    data = intelligence.campaign_stats.build(rw, funded['ws'], intelligence.today_msk(), now, days=7)
    sealed = now+timedelta(milliseconds=1)
    data['provenance'][0]['sealed_at'] = sealed.isoformat()
    calls = 0
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            nonlocal calls
            calls += 1
            return now if calls == 1 else now+timedelta(milliseconds=2)
    monkeypatch.setattr(intelligence, 'datetime', Clock)
    monkeypatch.setattr(intelligence.campaign_stats, 'build', lambda *args, **kwargs: data)
    response = req(insights_api, rw, funded, 'intelligence/snapshot-analysis?days=7')
    assert response.status_code == 200, response.text
    assert datetime.fromisoformat(response.json()['result']['context']['as_of']) >= sealed
