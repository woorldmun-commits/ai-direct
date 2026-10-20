"""Workspace insights contracts, parser, tenancy, money and deletion on disposable PostgreSQL."""
from datetime import date
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.api.app import PREFIX, create_app
from app.api.workspace_insights import router
from app.insights.lead_import import InvalidImport, parse
from app.insights.report import spend
from app.tenancy import workspace_scope
from test_api_support import client_for, cookie, session, settings, user, world  # noqa: F401
from test_lifecycle import sync
from test_schema import chain, new_workspace, one  # noqa: F401

PERIOD = {'period_from': '2026-09-20', 'period_to': '2026-09-26'}
HEADER = 'external_id,created_on,status,updated_on,direct_account_id,acquired_on,campaign_id\n'


@pytest.fixture(scope='session', autouse=True)
def insight_schema(db):
    with db('app_migrator') as conn:
        if conn.execute("SELECT to_regclass('workspace_leads')").fetchone()[0] is None:
            conn.execute((Path(__file__).parents[1]/'migrations/versions/0006_workspace_insights.sql').read_text(encoding='utf-8-sig'))


@pytest.fixture
def insights_api(db):
    app = create_app(settings(db))
    if not any(getattr(r, 'path', '').endswith('/insights') for r in app.routes):
        app.include_router(router, prefix=PREFIX)
    with client_for(app) as c:
        yield c


@pytest.fixture
def funded(rw, chain):
    sync(rw, chain['ws'], chain['account'], chain['release'], 100)
    return chain


def req(client, rw, chain, suffix='', body=None, actor=None):
    headers = {**cookie(session(rw, actor or chain['user'])), 'Origin': 'https://app.example.test'}
    url = f"/api/v1/workspaces/ws_{chain['ws']}/{suffix or 'insights'}"
    return client.get(url, headers=headers) if body is None else client.post(url, headers=headers, json=body)


def csv_for(chain, *, uid=None, status='qualified', acquired='2026-09-22', updated='2026-09-24', campaign='12345'):
    return HEADER + f"{uid or uuid4()},2026-09-23,{status},{updated},acc_{chain['account']},{acquired},{campaign}\n"


def test_empty_is_unavailable(insights_api, rw):
    owner = user(rw)
    ws = new_workspace(rw, user=owner)
    body = req(insights_api, rw, {'ws': ws, 'user': owner}).json()
    assert body['budget']['actual']['amount'] is None
    assert body['lead_quality']['qcpl']['amount'] is None
    assert body['lead_quality']['coverage']['matched_pct'] is None
    assert body['summary']['delivery'] == 'manual_pull'
    assert all(c['status'] == 'unavailable' for c in body['health']['checks'])


def test_budget_is_decimal_and_same_complete_period(insights_api, rw, funded):
    r = req(insights_api, rw, funded, 'budget-plan', {**PERIOD, 'amount': '1000.10'})
    assert r.status_code == 200, r.text
    body = req(insights_api, rw, funded).json()
    assert body['budget']['plan']['amount'] == '1000.10'
    assert body['budget']['actual']['amount'] == '700.00'
    assert body['budget']['variance']['amount'] == '-300.10'
    # A later, partially covered period is not silently reported as zero or the earlier seven-day spend.
    assert req(insights_api, rw, funded, 'budget-plan', {'period_from': '2026-09-25', 'period_to': '2026-09-30', 'amount': '1000'}).status_code == 200
    assert req(insights_api, rw, funded).json()['budget']['actual']['amount'] is None


@pytest.mark.parametrize('amount', ['NaN', 'Infinity', '-1', '0', '1.001', '1e3', 100.1, True])
def test_bad_budget_money(insights_api, rw, funded, amount):
    assert req(insights_api, rw, funded, 'budget-plan', {**PERIOD, 'amount': amount}).status_code == 400


def test_import_idempotent_and_no_cohort_claim_no_qcpl(insights_api, rw, funded):
    uid = str(uuid4())
    body = {'csv': csv_for(funded, uid=uid), **PERIOD}
    for _ in range(2):
        r = req(insights_api, rw, funded, 'lead-import', body)
        assert r.status_code == 200, r.text
    assert one(rw, 'SELECT count(*) FROM workspace_leads WHERE workspace_id=%s', funded['ws']) == 1
    report = req(insights_api, rw, funded).json()['lead_quality']
    assert report['qcpl']['amount'] is None
    assert report['reason'] == 'cohort_completeness_unverified'
    assert uid not in str(report)


def test_declared_same_acquisition_cohort_qcpl(insights_api, rw, funded):
    r = req(insights_api, rw, funded, 'lead-import', {'csv': csv_for(funded), **PERIOD, 'cohort_complete': True})
    assert r.status_code == 200, r.text
    body = req(insights_api, rw, funded).json()['lead_quality']
    assert body['counts'] == {'total': 1, 'qualified': 1, 'unresolved': 0, 'matched': 1}
    assert body['qcpl']['amount'] == '700.00'
    assert body['qcpl']['source'] == 'yandex_direct+user_input'
    assert body['coverage']['completeness_source'] == 'user_input'


def test_status_update_not_duplicate_and_stale_import_atomic(insights_api, rw, funded):
    uid = str(uuid4())
    assert req(insights_api, rw, funded, 'lead-import', {'csv': csv_for(funded, uid=uid, status='new'), **PERIOD}).status_code == 200
    assert req(insights_api, rw, funded, 'lead-import', {'csv': csv_for(funded, uid=uid, status='qualified', updated='2026-09-25'), **PERIOD}).status_code == 200
    assert one(rw, 'SELECT count(*) FROM workspace_leads WHERE workspace_id=%s', funded['ws']) == 1
    new = csv_for(funded).splitlines()[1]
    old = csv_for(funded, uid=uid, status='new').splitlines()[1]
    r = req(insights_api, rw, funded, 'lead-import', {'csv': HEADER+new+'\n'+old+'\n', **PERIOD})
    assert r.status_code == 400 and uid not in r.text
    assert one(rw, 'SELECT count(*) FROM workspace_leads WHERE workspace_id=%s', funded['ws']) == 1


@pytest.mark.parametrize('status,campaign,reason', [('new', '12345', 'qualification_incomplete'),
                                                  ('qualified', '99999', 'scope_or_period_unmatched'),
                                                  ('rejected', '12345', 'no_qualified_leads')])
def test_qcpl_withheld_for_invalid_denominator(insights_api, rw, funded, status, campaign, reason):
    r = req(insights_api, rw, funded, 'lead-import', {'csv': csv_for(funded, status=status, campaign=campaign), **PERIOD, 'cohort_complete': True})
    assert r.status_code == 200, r.text
    q = req(insights_api, rw, funded).json()['lead_quality']
    assert q['qcpl']['amount'] is None and q['reason'] == reason


def test_no_cross_workspace_account_or_leak(insights_api, rw, funded, world):
    own = csv_for(funded)
    bad = own.replace(f"acc_{funded['account']}", f"acc_{world['rec_b1']['account']}")
    r = req(insights_api, rw, funded, 'lead-import', {'csv': bad})
    assert r.status_code == 400 and 'acc_' not in r.text
    assert req(insights_api, rw, funded, actor=world['owner_b']).status_code == 404
    assert insights_api.get(f"/api/v1/workspaces/ws_{funded['ws']}/insights").status_code == 401


@pytest.mark.parametrize('suffix,body', [('budget-plan', {**PERIOD, 'amount': '10'}), ('lead-import', {'csv': 'a\nb'})])
def test_viewer_cannot_write(insights_api, rw, world, suffix, body):
    r = req(insights_api, rw, {'ws': world['a1'], 'user': world['viewer']}, suffix, body)
    assert r.status_code == 403


def test_rls_and_database_foreign_account_constraint(db, rw, funded, world):
    body = {'csv': csv_for(funded)}
    from app.insights.lead_import import store
    store(rw, funded['ws'], parse(body['csv'], date(2026, 10, 18)), body['csv'], None, None, False)
    with db('app_rw') as conn:
        assert conn.execute('SELECT * FROM workspace_leads').fetchall() == []
        with workspace_scope(conn, world['b1']):
            assert conn.execute('SELECT * FROM workspace_leads').fetchall() == []
        with workspace_scope(conn, funded['ws']):
            assert len(conn.execute('SELECT * FROM workspace_leads').fetchall()) == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('UPDATE workspace_leads SET workspace_id=%s', (world['b1'],))
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute('''INSERT INTO workspace_leads (workspace_id,external_id,created_on,updated_on,direct_account_id,status)
                       VALUES (%s,%s,'2026-09-22','2026-09-22',%s,'new')''', (funded['ws'], uuid4(), world['rec_b1']['account']))


def test_workspace_deletion_cascades_insights(insights_api, db, rw, funded):
    assert req(insights_api, rw, funded, 'lead-import', {'csv': csv_for(funded)}).status_code == 200
    assert req(insights_api, rw, funded, 'budget-plan', {**PERIOD, 'amount': '100'}).status_code == 200
    rw.execute("UPDATE workspaces SET status='deletion_pending',deactivated_at=now() WHERE id=%s", (funded['ws'],))
    with db('app_deleter') as conn:
        conn.execute('SELECT delete_workspace_data(%s)', (funded['ws'],))
    for table in ('workspace_leads', 'workspace_lead_imports', 'workspace_budget_plans'):
        assert rw.execute(f'SELECT count(*) FROM {table} WHERE workspace_id=%s', (funded['ws'],)).fetchone()[0] == 0


@pytest.mark.parametrize('change', [lambda x: x.replace('external_id', 'email'),
                                    lambda x: x.replace('qualified', '=HYPERLINK("bad")'),
                                    lambda x: x+'\x00', lambda x: x.replace('2026-09-23','2026-99-23'),
                                    lambda x: x.replace('acc_1', 'phone_number'), lambda x: x.replace('2026-09-24','2026-09-21')])
def test_parser_rejects_untrusted_shape(change):
    text = csv_for({'account': 1})
    with pytest.raises(InvalidImport):
        parse(change(text), date(2026, 10, 18))


def test_csv_duplicate_and_row_bounds():
    text = csv_for({'account': 1})
    with pytest.raises(InvalidImport):
        parse(text+text.splitlines()[1]+'\n', date(2026, 10, 18))
    with pytest.raises(InvalidImport):
        parse('x'*48001, date(2026, 10, 18))


def test_multi_account_cohort_spend_excludes_unimported_accounts(insights_api, rw, funded):
    from test_schema import connected
    other = one(rw, 'INSERT INTO direct_accounts (direct_connection_id,is_selected) VALUES (%s,true) RETURNING id',
                connected(rw, 'direct', funded['ws'], f"extra-{funded['ws']}"))
    sync(rw, funded['ws'], other, funded['release'], 900)
    # Repeated snapshots for one account must replace, not add to each other.
    sync(rw, funded['ws'], funded['account'], funded['release'], 200)
    assert req(insights_api, rw, funded, 'lead-import', {'csv': csv_for(funded), **PERIOD, 'cohort_complete': True}).status_code == 200
    body = req(insights_api, rw, funded).json()
    assert body['budget']['actual']['amount'] == '7700.00'
    assert body['lead_quality']['qcpl']['amount'] == '1400.00'


def test_empty_import_period_rejected_not_internal(insights_api, rw, funded):
    r = req(insights_api, rw, funded, 'lead-import', {'csv': csv_for(funded), 'period_from':'', 'period_to':'', 'cohort_complete': True})
    assert r.status_code == 400


def test_complete_cohort_needs_acquisition_date(insights_api, rw, funded):
    r = req(insights_api, rw, funded, 'lead-import', {'csv': csv_for(funded, acquired=''), **PERIOD, 'cohort_complete': True})
    assert r.status_code == 400 and r.json()['error']['reason'] == 'acquisition_date_required'


def test_account_failure_and_one_stale_account_not_masked(insights_api, rw, funded):
    rw.execute("UPDATE direct_accounts SET status='unavailable',unavailable_reason='access_denied' WHERE id=%s", (funded['account'],))
    checks = {r['id']: r for r in req(insights_api, rw, funded).json()['health']['checks']}
    assert checks['direct']['status'] == 'attention'
    assert checks['freshness']['status'] == 'attention'


def test_csv_exact_row_limit_and_nonrub_refund_validation():
    text = HEADER + ''.join(csv_for({'account':1}).splitlines()[1]+'\n' for _ in range(501))
    with pytest.raises(InvalidImport):
        parse(text, date(2026,10,18))
    txt = 'external_id,created_on,status,updated_on,direct_account_id,amount,currency,refund_amount\n'
    txt += f'{uuid4()},2026-09-22,refunded,2026-09-24,acc_1,10.00,RUB,11.00\n'
    with pytest.raises(InvalidImport):
        parse(txt, date(2026,10,18))
