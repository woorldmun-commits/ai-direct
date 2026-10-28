import json
from datetime import datetime, timedelta, timezone

import pytest
from psycopg.types.json import Jsonb

from app.insights.product_usage import build
from test_schema import chain, new_workspace  # noqa: F401

START = datetime(2026, 10, 1, tzinfo=timezone.utc)
END = START + timedelta(days=7)


@pytest.mark.parametrize('ws,frm,to', [(True, START, END), (0, START, END),
    (1, START.replace(tzinfo=None), END), (1, END, START), (1, START, START)])
def test_usage_rejects_invalid_scope_before_database(ws, frm, to):
    with pytest.raises(ValueError):
        build(None, ws, frm, to)


def test_usage_is_scoped_deduplicated_bounded_and_private(db, rw, chain):
    other = new_workspace(rw, 'other')
    for ws, rec, at in [(chain['ws'], 9001, START), (chain['ws'], 9001, START),
                        (chain['ws'], 9002, END-timedelta(seconds=1)),
                        (chain['ws'], 9003, END), (chain['ws'], 9004, START-timedelta(seconds=1)),
                        (other, 9005, START)]:
        rw.execute('''INSERT INTO outbox_events
            (workspace_id,event_type,aggregate_type,aggregate_id,payload,created_at)
            VALUES (%s,'recommendation_created','recommendation',%s,%s,%s)''',
            (ws, rec, Jsonb({'private_marker': 'must_not_leave_database'}), at))
    for at in (START, START, END):
        rw.execute('''INSERT INTO recommendation_events
            (recommendation_id,type,actor_user_id,payload,created_at)
            VALUES (%s,'rejected',%s,%s,%s)''',
            (chain['rec'], chain['user'], Jsonb({'private_marker': 'must_not_leave_database'}), at))
    with db('app_rw') as conn:
        report = build(conn, chain['ws'], START, END)
        foreign = build(conn, other, START, END)
        assert conn.execute("SELECT current_setting('app.workspace_id',true)").fetchone()[0] in ('', None)
    assert report['counts']['recommendation_created'] == {'events': 3, 'unique_recommendations': 2}
    assert report['counts']['rejected'] == {'events': 2, 'unique_recommendations': 1}
    assert foreign['counts']['recommendation_created'] == {'events': 1, 'unique_recommendations': 1}
    assert foreign['counts']['rejected']['events'] == 0
    assert report['time_to_first_audit_seconds'] is None
    encoded = json.dumps(report)
    assert 'must_not_leave_database' not in encoded
    assert not any(key in encoded for key in ('workspace_id', 'actor_user_id', 'payload', 'recommendation_id'))


def test_usage_refuses_system_role(rw, chain):
    with pytest.raises(ValueError, match='app_rw'):
        build(rw, chain['ws'], START, END)


def test_activation_uses_workspace_creation_and_first_audit_without_claiming_usefulness(db, rw, chain):
    created = rw.execute('SELECT created_at FROM workspaces WHERE id=%s', (chain['ws'],)).fetchone()[0]
    first = rw.execute('SELECT min(created_at) FROM audit_runs WHERE workspace_id=%s', (chain['ws'],)).fetchone()[0]
    with db('app_rw') as conn:
        report = build(conn, chain['ws'], created - timedelta(hours=1), first + timedelta(hours=1))
        before_audit = build(conn, chain['ws'], created - timedelta(hours=1), first)
    assert report['time_to_first_audit_seconds'] == (first - created).total_seconds()
    assert report['activation']['started_at'] == created.isoformat()
    assert report['activation']['first_recorded_audit_at'] == first.isoformat()
    assert before_audit['time_to_first_audit_seconds'] is None
    assert 'not_user_views_or_proven_usefulness' in report['limitations']
