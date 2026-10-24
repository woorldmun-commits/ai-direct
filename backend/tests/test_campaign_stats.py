from decimal import Decimal
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
import json

import pytest

from test_workspace_insights import funded, insights_api, req  # noqa: F401
from test_schema import chain  # noqa: F401
from test_lifecycle import sync
from test_api_support import user
from app.insights import campaign_stats


def test_campaign_totals_series_and_real_detail(insights_api, rw, funded):
    response = req(insights_api, rw, funded, 'campaign-stats?days=7')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['summary']['cost']['amount'] == '700.00'
    assert body['summary']['conversions']['amount'] == '7.00'
    assert len(body['daily']) == 7
    assert sum(Decimal(d['metrics']['cost']['amount']) for d in body['daily']) == Decimal('700')
    assert sum(Decimal(c['metrics']['cost']['amount']) for c in body['campaigns']) == Decimal('700')
    assert body['scope']['complete']
    assert body['summary']['cost']['data_status'] == 'partial'
    detail = req(insights_api, rw, funded, f"campaign-stats?days=7&ad_account=acc_{funded['account']}&campaign_id=12345")
    assert detail.status_code == 200
    assert detail.json()['summary'] == body['summary']
    assert req(insights_api, rw, funded, f"campaign-stats?ad_account=acc_{funded['account']}&campaign_id=99999").status_code == 404


def test_resnapshot_does_not_double_spend(insights_api, rw, funded):
    sync(rw, funded['ws'], funded['account'], funded['release'], 200)
    body = req(insights_api, rw, funded, 'campaign-stats?days=7').json()
    assert body['summary']['cost']['amount'] == '1400.00'
    assert len(body['provenance']) == 1


def test_account_selection_and_tenant_guard(insights_api, rw, funded):
    assert req(insights_api, rw, funded, 'campaign-stats', actor=user(rw)).status_code == 404
    assert req(insights_api, rw, funded, 'campaign-stats?ad_account=acc_999999999').status_code == 404
    rw.execute('UPDATE direct_accounts SET is_selected=false WHERE id=%s', (funded['account'],))
    body = req(insights_api, rw, funded, 'campaign-stats').json()
    assert body['summary']['cost']['amount'] is None
    assert body['campaigns'] == []
    assert not body['scope']['complete']
    assert req(insights_api, rw, funded, f"campaign-stats?ad_account=acc_{funded['account']}").status_code == 404


@pytest.mark.parametrize('query', ['days=8', 'days=365', 'ad_account=acc_0', 'campaign_id=12345', 'campaign_id=1%27', 'ad_account=acc_9999999999999999999', 'offset=20001'])
def test_bad_scope_is_rejected(insights_api, rw, funded, query):
    assert req(insights_api, rw, funded, 'campaign-stats?'+query).status_code in (400, 422)


def resnapshot_with_conversions(rw, data, conversions):
    run = rw.execute("INSERT INTO sync_runs(workspace_id,direct_account_id,kind) VALUES(%s,%s,'scheduled') RETURNING id", (data['ws'],data['account'])).fetchone()[0]
    rw.execute("UPDATE sync_runs SET status='running',started_at=now() WHERE id=%s", (run,))
    rw.execute("UPDATE sync_runs SET status='succeeded',finished_at=now() WHERE id=%s", (run,))
    previous = rw.execute('SELECT id FROM snapshots WHERE workspace_id=%s ORDER BY sealed_at DESC,id DESC LIMIT 1', (data['ws'],)).fetchone()[0]
    snapshot = rw.execute('''INSERT INTO snapshots(workspace_id,sync_run_id,release_id,period_from,period_to,data_until,partial_from,sources,conversion_definition)
        SELECT workspace_id,%s,release_id,period_from,period_to,data_until,partial_from,sources,conversion_definition FROM snapshots WHERE id=%s RETURNING id''', (run,previous)).fetchone()[0]
    rw.execute('''INSERT INTO stat_rows(snapshot_id,source,level,object_id,campaign_id,date,impressions,clicks,cost,conversions)
        SELECT %s,source,level,object_id,campaign_id,date,impressions,clicks,cost,%s FROM stat_rows WHERE snapshot_id=%s''', (snapshot,conversions,previous))
    rw.execute("UPDATE snapshots SET status='complete',sealed_at=now() WHERE id=%s", (snapshot,))


@pytest.mark.parametrize('conversions', [None, 0])
def test_missing_and_zero_conversions_never_create_cpa(insights_api, rw, funded, conversions):
    resnapshot_with_conversions(rw,funded,conversions)
    body = req(insights_api,rw,funded,'campaign-stats?days=7').json()
    assert body['summary']['cost']['amount'] == '700.00'
    assert body['summary']['cpa']['amount'] is None
    assert body['summary']['conversions']['amount'] == (None if conversions is None else '0.00')
    assert all(d['metrics']['cpa']['amount'] is None for d in body['daily'])


def test_big_campaign_id_rejected_before_sql(insights_api, rw, funded):
    response = req(insights_api,rw,funded,f"campaign-stats?ad_account=acc_{funded['account']}&campaign_id=9999999999999999999")
    assert response.status_code == 400


def test_large_campaign_page_keeps_complete_totals_under_bridge_limit(monkeypatch):
    start = date(2026, 9, 1)
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(campaign_stats, 'selected_accounts', lambda *_: [(1, 'connected')])
    monkeypatch.setattr(campaign_stats, 'load_state', lambda *_: None)
    monkeypatch.setattr(campaign_stats, 'direct_unavailable', lambda *_: None)
    rows = [(1, 2, campaign, start+timedelta(days=day), Decimal('1.00'), 1, 10, Decimal(1))
            for campaign in range(1, 1001) for day in range(7)]
    snapshot = (2,start,start+timedelta(days=6),start+timedelta(days=5),now,{'goal_ids':[1]})
    conn = SimpleNamespace(execute=lambda sql, params: SimpleNamespace(fetchone=lambda:snapshot,fetchall=lambda:rows))
    first = campaign_stats.build(conn,1,now.date(),now,7)
    second = campaign_stats.build(conn,1,now.date(),now,7,offset=200)
    assert first['campaign_count'] == 1000 and first['next_offset'] == 200
    assert len(first['campaigns']) == 200
    assert first['summary']['cost']['amount'] == '7000.00'
    assert second['summary'] == first['summary'] and second['daily'] == first['daily']
    assert {c['campaign_id'] for c in first['campaigns']}.isdisjoint(c['campaign_id'] for c in second['campaigns'])
    assert len(json.dumps(first).encode()) < 1_048_576


@pytest.mark.parametrize('different_days', [False, True])
@pytest.mark.parametrize('missing_definition', [False, True])
def test_incompatible_goals_and_missing_days_are_unavailable(monkeypatch, different_days, missing_definition):
    start = date(2026,9,1)
    now = datetime(2026,9,10,tzinfo=timezone.utc)
    monkeypatch.setattr(campaign_stats, 'selected_accounts', lambda *_:[(1,'connected'),(2,'connected')])
    monkeypatch.setattr(campaign_stats, 'load_state', lambda *_:None)
    monkeypatch.setattr(campaign_stats, 'direct_unavailable', lambda *_:None)
    rows = [(aid,aid,123,start+timedelta(days=aid-1 if different_days else 0),Decimal('10.00'),1,10,Decimal(1)) for aid in (1,2)]
    def execute(sql,params):
        snapshot=(params[1],start,start+timedelta(days=6),start+timedelta(days=5),now,None if missing_definition and params[1]==2 else {'goal_ids':[params[1]]})
        return SimpleNamespace(fetchone=lambda:snapshot,fetchall=lambda:rows)
    result=campaign_stats.build(SimpleNamespace(execute=execute),1,now.date(),now,7)
    assert result['summary']['cost']['amount']=='20.00'
    assert result['summary']['conversions']['amount'] is None
    assert result['summary']['cpa']['amount'] is None
    assert all(d['metrics']['conversions']['amount'] is None for d in result['daily'])
    assert Decimal(result['campaigns'][0]['metrics']['conversions']['amount'])==1
    assert Decimal(result['campaigns'][0]['metrics']['cpa']['amount'])==10
    assert result['campaigns'][1]['metrics']['conversions']['amount'] == (None if missing_definition else '1')
    assert result['campaigns'][1]['metrics']['cpa']['amount'] == (None if missing_definition else '10.00')
    assert result['daily'][2]['metrics']['cost']['amount'] is None
