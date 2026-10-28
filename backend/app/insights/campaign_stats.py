"""Read-only campaign observations from one latest sealed snapshot per selected account."""
import json
from datetime import timedelta
from decimal import Decimal

from app.api.errors import ApiError
from app.api.serialize import value_of
from app.contract import Value
from app.insights.report import selected_accounts
from app.worker.guard import direct_unavailable, load_state


def build(conn, ws, today, now, days=30, account=None, campaign=None, offset=0):
    selected = selected_accounts(conn, ws)
    options = [f'acc_{aid}' for aid, _ in selected]
    if account is not None and account not in {a for a, _ in selected}:
        raise ApiError(404, 'not_found')
    selected = [(a, s) for a, s in selected if account is None or a == account]
    included, excluded = [], []
    for aid, _ in selected:
        reason = direct_unavailable(load_state(conn, ws, aid, now))
        row = None if reason else conn.execute('''
            SELECT s.id,s.period_from,s.period_to,s.partial_from,s.sealed_at,s.conversion_definition
            FROM snapshots s JOIN sync_runs r ON r.id=s.sync_run_id
            WHERE s.workspace_id=%s AND r.direct_account_id=%s AND s.status='complete'
            ORDER BY s.sealed_at DESC,s.id DESC LIMIT 1''', (ws, aid)).fetchone()
        if row is None:
            excluded.append({'ad_account': f'acc_{aid}', 'reason': reason or 'no_snapshot'})
        else:
            included.append((aid, *row))
    end = min((r[3] for r in included), default=today-timedelta(days=1))
    start = end-timedelta(days=days-1)
    covered = []
    for row in included:
        if row[2] > start or row[3] < end:
            excluded.append({'ad_account': f'acc_{row[0]}', 'reason': 'period_not_covered'})
        else:
            covered.append(row)
    snapshots = [r[1] for r in covered]
    rows = conn.execute('''
        SELECT r.direct_account_id,x.snapshot_id,x.campaign_id,x.date,
               sum(x.cost),sum(x.clicks),sum(x.impressions),
               CASE WHEN count(*)=count(x.conversions) THEN sum(x.conversions) END
        FROM stat_rows x JOIN snapshots s ON s.id=x.snapshot_id JOIN sync_runs r ON r.id=s.sync_run_id
        WHERE s.workspace_id=%s AND x.snapshot_id=ANY(%s) AND x.source='yandex_direct'
          AND x.level='campaign' AND x.date BETWEEN %s AND %s
          AND (%s::bigint IS NULL OR x.campaign_id=%s)
        GROUP BY r.direct_account_id,x.snapshot_id,x.campaign_id,x.date
        ORDER BY r.direct_account_id,x.campaign_id,x.date LIMIT 20001''',
        (ws, snapshots, start, end, campaign, campaign)).fetchall() if snapshots else []
    if len(rows) > 20000:
        raise ApiError(400, 'invalid_request', 'scope_too_large')
    if campaign is not None and not rows:
        raise ApiError(404, 'not_found')
    definitions = {json.dumps(r[6], sort_keys=True) for r in covered}
    conversions_compatible = len(definitions) == 1 and all(r[6] is not None for r in covered)
    observed_accounts = {row[0] for row in rows}
    for aid, *_ in covered:
        if aid not in observed_accounts:
            excluded.append({'ad_account': f'acc_{aid}', 'reason': 'campaign_rows_missing'})
    provenance = [{'ad_account': f'acc_{r[0]}', 'snapshot_id': str(r[1]),
                   'sealed_at': r[5].isoformat(), 'partial_from': r[4].isoformat(),
                   'conversion_definition': r[6]} for r in covered]
    partial_by_snap = {r[1]: r[4] for r in covered}
    definition_by_snap = {r[1]: json.dumps(r[6], sort_keys=True) if r[6] is not None else None for r in covered}

    def metrics(observations, frm, to, campaign_scope=False):
        partial = bool(excluded) or any(r[3] >= partial_by_snap[r[1]] for r in observations)
        snapshot = max((r[1] for r in observations), default=0)
        def value(amount, unit, formula, reason='no_data'):
            return value_of(Value(amount=amount, unit=unit, source='yandex_direct', period_from=frm, period_to=to,
                calculation_type='unavailable' if amount is None else 'actual', data_status='partial' if partial else 'complete',
                data_sufficiency='insufficient' if amount is None else 'sufficient', snapshot_id=snapshot,
                formula=formula, unavailable_reason=reason if amount is None else None))
        cost = sum((r[4] for r in observations), Decimal(0)) if observations else None
        clicks = sum(r[5] for r in observations) if observations else None
        impressions = sum(r[6] for r in observations) if observations else None
        observation_definitions = {definition_by_snap[r[1]] for r in observations}
        compatible = (len(observation_definitions) == 1 and None not in observation_definitions) if campaign_scope else conversions_compatible
        conversions = sum(r[7] for r in observations) if observations and compatible and all(r[7] is not None for r in observations) else None
        cpa = (cost / conversions).quantize(Decimal('.01')) if conversions else None
        return {'cost': value(cost, 'rub', 'sum(campaign cost); one latest snapshot per account'),
                'clicks': value(clicks, 'count', 'sum(campaign clicks)'),
                'impressions': value(impressions, 'count', 'sum(campaign impressions)'),
                'conversions': value(conversions, 'count', 'sum(campaign conversions); compatible definitions'),
                'cpa': value(cpa, 'rub', 'sum(cost) / sum(conversions)', 'no_conversions' if conversions == 0 else 'no_data')}

    daily = [{'date': (day := start+timedelta(days=i)).isoformat(),
              'metrics': metrics([r for r in rows if r[3] == day], day, day)} for i in range(days)]
    keys = sorted({(r[0], r[2]) for r in rows})
    campaigns = [{'ad_account': f'acc_{aid}', 'campaign_id': str(cid),
                  'metrics': metrics([r for r in rows if r[0] == aid and r[2] == cid], start, end, campaign_scope=True)} for aid, cid in keys[offset:offset+200]]
    return {'period': {'from': start.isoformat(), 'to': end.isoformat()}, 'accounts': options,
            'scope': {'selected': len(selected), 'included': len(observed_accounts), 'excluded': excluded,
                      'complete': bool(rows) and not excluded},
            'provenance': provenance, 'summary': metrics(rows, start, end), 'daily': daily, 'campaigns': campaigns,
            'campaign_count': len(keys), 'next_offset': offset+200 if offset+200<len(keys) else None,
            'limitations': ['Названия, статусы и разделение Поиск/РСЯ не передаются источником снимков.',
                            'Отсутствующие наблюдения не считаются нулём. Последние дни могут уточняться.']
                            + ([] if conversions_compatible else ['Определения конверсий отсутствуют или несовместимы; общие конверсии и CPA скрыты.'])}
