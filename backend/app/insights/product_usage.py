"""Workspace usage aggregates from existing domain records; no tracking SDK or payload export."""
from datetime import datetime

from app.tenancy import workspace_scope

LIFECYCLE = ('recommendation_created', 'recommendation_resolved', 'recommendation_measured')
DECISIONS = ('rejected', 'postponed', 'checked', 'done')


def build(conn, workspace_id: int, from_at: datetime, to_at: datetime) -> dict:
    """Read-only [from_at,to_at) report. Caller is an authorized workspace operator."""
    if (isinstance(workspace_id, bool) or not isinstance(workspace_id, int) or workspace_id < 1
            or not isinstance(from_at, datetime) or not isinstance(to_at, datetime)
            or from_at.utcoffset() is None or to_at.utcoffset() is None or from_at >= to_at):
        raise ValueError('positive workspace and ordered timezone-aware timestamps required')
    if not conn.autocommit:
        raise ValueError('autocommit connection required')
    with workspace_scope(conn, workspace_id), conn.transaction():
        conn.execute('SET TRANSACTION READ ONLY')
        conn.execute("SET LOCAL statement_timeout = '15s'")
        if conn.execute('SELECT current_user').fetchone()[0] != 'app_rw':
            raise ValueError('app_rw role required')
        workspace = conn.execute('SELECT created_at FROM workspaces WHERE id=%s', (workspace_id,)).fetchone()
        if workspace is None:
            raise ValueError('workspace unavailable')
        first_audit = conn.execute('''SELECT min(created_at) FROM audit_runs
            WHERE workspace_id=%s AND created_at >= %s AND created_at < %s''',
            (workspace_id, workspace[0], to_at)).fetchone()[0]
        audits = conn.execute('''SELECT count(*),min(created_at),max(created_at) FROM audit_runs
            WHERE workspace_id=%s AND created_at >= %s AND created_at < %s''',
            (workspace_id, from_at, to_at)).fetchone()
        lifecycle = conn.execute('''SELECT event_type,count(*),count(DISTINCT aggregate_id)
            FROM outbox_events WHERE workspace_id=%s AND aggregate_type='recommendation'
            AND created_at >= %s AND created_at < %s AND event_type=ANY(%s)
            GROUP BY event_type''', (workspace_id, from_at, to_at, list(LIFECYCLE))).fetchall()
        # Same parent join as api.workspace_insights.weekly_report; distinct IDs avoid repeat-event inflation.
        decisions = conn.execute('''SELECT e.type,count(*),count(DISTINCT e.recommendation_id)
            FROM recommendation_events e JOIN recommendations r ON r.id=e.recommendation_id
            JOIN issues i ON i.id=r.issue_id WHERE i.workspace_id=%s
            AND e.created_at >= %s AND e.created_at < %s AND e.type=ANY(%s)
            GROUP BY e.type''', (workspace_id, from_at, to_at, list(DECISIONS))).fetchall()
        history = {kind: conn.execute(f'SELECT count(*) FROM intelligence_{kind} WHERE workspace_id=%s',
                                     (workspace_id,)).fetchone()[0] for kind in ('profiles', 'imports', 'runs')}
    counts = {name: {'events': 0, 'unique_recommendations': 0} for name in (*LIFECYCLE, *DECISIONS)}
    for name, events, unique in (*lifecycle, *decisions):
        counts[name] = {'events': events, 'unique_recommendations': unique}
    return {'period': {'from_inclusive': from_at.isoformat(), 'to_exclusive': to_at.isoformat()},
            'audits': {'records': audits[0],
                       'first_recorded_in_window': audits[1].isoformat() if audits[1] else None,
                       'last_recorded_in_window': audits[2].isoformat() if audits[2] else None},
            'counts': counts,
            'intelligence_history': {'current_records': history},
            'time_to_first_audit_seconds': (first_audit - workspace[0]).total_seconds() if first_audit else None,
            'activation': {'definition': 'workspace_created_to_first_recorded_audit',
                           'started_at': workspace[0].isoformat(),
                           'first_recorded_audit_at': first_audit.isoformat() if first_audit else None},
            'limitations': ['recorded_domain_activity_only', 'not_user_views_or_proven_usefulness',
                            'not_a_cohort_conversion_rate', 'workspace_creation_is_not_first_use',
                            'outbox_retention_limits_history', 'not_causal_savings']}
