"""Deterministic insights. No LLM or fabricated denominator/causal effect."""
from datetime import timedelta
from decimal import Decimal

from app.api.serialize import value_of
from app.api.today import _freshness
from app.contract import Value

CENT = Decimal('.01')
LEAD_REASONS = {
    'no_imported_leads': 'заявки ещё не импортированы.',
    'cohort_completeness_unverified': 'подтвердите полноту когорты за выбранный период.',
    'acquisition_date_missing': 'заполните дату привлечения каждой заявки.',
    'qualification_incomplete': 'завершите квалификацию новых заявок.',
    'scope_or_period_unmatched': 'проверьте соответствие периода, аккаунтов и кампаний.',
    'no_qualified_leads': 'за период нет квалифицированных заявок.',
    'no_selected_accounts': 'выберите рекламные аккаунты.',
    'campaign_rows_missing': 'нет данных по кампаниям за выбранный период.',
    'period_not_fully_covered': 'нужны полные окончательные данные за тот же период.',
}


def metric(amount, frm, to, *, unit='rub', source='yandex_direct', formula=None, snapshot=0,
           partial=False, estimated=False):
    return value_of(Value(amount=amount, unit=unit, source=source, period_from=frm, period_to=to,
                         calculation_type='unavailable' if amount is None else 'estimated' if estimated else 'actual',
                         data_status='partial' if partial else 'complete',
                         data_sufficiency='insufficient' if amount is None else 'sufficient',
                         snapshot_id=snapshot, formula=formula,
                         unavailable_reason='no_data' if amount is None else None))


def selected_accounts(conn, ws):
    return conn.execute('''SELECT a.id,CASE WHEN a.status='unavailable' THEN 'account_unavailable' ELSE c.status END FROM direct_accounts a JOIN direct_connections c
                           ON c.id=a.direct_connection_id WHERE c.workspace_id=%s AND a.is_selected ORDER BY a.id''',
                        (ws,)).fetchall()


def spend(conn, ws, frm, to, accounts, *, allow_partial=False):
    """Latest sealed snapshot per selected account, covering entire same period; no snapshot summation."""
    if not accounts:
        return metric(None, frm, to), {}, 'no_selected_accounts'
    snaps = conn.execute('''SELECT DISTINCT ON (r.direct_account_id) r.direct_account_id,s.id,
                           s.period_from,s.period_to,s.partial_from
                           FROM snapshots s JOIN sync_runs r ON r.id=s.sync_run_id
                           WHERE s.workspace_id=%s AND s.status='complete' AND r.direct_account_id=ANY(%s)
                           ORDER BY r.direct_account_id,s.sealed_at DESC,s.id DESC''', (ws, accounts)).fetchall()
    if len(snaps) != len(accounts) or any(a > frm or b < to or (p <= to and not allow_partial) for _, _, a, b, p in snaps):
        return metric(None, frm, to), {}, 'period_not_fully_covered'
    ids = [r[1] for r in snaps]
    rows = conn.execute('''SELECT s.snapshot_id,s.campaign_id,sum(s.cost) FROM stat_rows s
                           WHERE s.snapshot_id=ANY(%s) AND s.source='yandex_direct' AND s.level='campaign'
                           AND s.date BETWEEN %s AND %s GROUP BY s.snapshot_id,s.campaign_id''',
                        (ids, frm, to)).fetchall()
    if not rows or set(ids) != {r[0] for r in rows}:
        return metric(None, frm, to), {}, 'campaign_rows_missing'
    by_snap = {r[1]: r[0] for r in snaps}
    campaigns = {(by_snap[s], c): cost for s, c, cost in rows}
    total = sum(campaigns.values(), Decimal('0')).quantize(CENT)
    return metric(total, frm, to, snapshot=max(ids), partial=any(p <= to for _, _, _, _, p in snaps),
                  formula='sum(cost), one latest snapshot per account'), campaigns, None


def health(conn, ws, today, accounts):
    fresh = _freshness(conn, ws)
    checks = []
    def check(key, status, reason, action):
        checks.append({'id': key, 'status': status, 'reason': reason, 'action': action})
    if not accounts:
        check('direct', 'unavailable', 'no_selected_accounts', 'Выберите аккаунт Директа в подключениях.')
    elif any(s != 'connected' for _, s in accounts):
        check('direct', 'attention', 'connection_unavailable', 'Проверьте доступ и переподключите Директ.')
    else:
        check('direct', 'ok', 'selected_connections_connected', 'Подключения выбранных аккаунтов доступны.')
    stale, missing_goals = 0, 0
    for aid, _ in accounts:
        row = conn.execute('''SELECT s.period_to,s.conversion_definition FROM snapshots s
                              JOIN sync_runs r ON r.id=s.sync_run_id WHERE s.workspace_id=%s
                              AND s.status='complete' AND r.direct_account_id=%s
                              ORDER BY s.sealed_at DESC,s.id DESC LIMIT 1''', (ws, aid)).fetchone()
        stale += int(row is None or row[0] < today-timedelta(days=2))
        missing_goals += int(row is None or row[1] is None)
    check('freshness', 'unavailable' if not accounts else 'attention' if stale else 'ok',
          'selected_accounts_stale' if stale else 'no_selected_accounts' if not accounts else 'recent_snapshots',
          'Проверьте синхронизацию каждого выбранного аккаунта.' if stale else 'Даты данных указаны ниже.')
    check('goals', 'unavailable' if not accounts else 'attention' if missing_goals else 'ok',
          'conversion_definition_missing' if missing_goals else 'no_selected_accounts' if not accounts else 'definition_present',
          'Выберите счётчик и цели Метрики; наличие определения не подтверждает качество цели.')
    metrika = fresh['yandex_metrika']['status']
    check('metrika', 'ok' if metrika == 'connected' else 'unavailable' if metrika is None else 'attention',
          'connected' if metrika == 'connected' else 'metrika_not_connected',
          'Проверьте счётчик, цели и права Метрики.')
    return {'checks': checks, 'freshness': fresh}


def lead_quality(conn, ws, frm, to, accounts):
    rows = conn.execute('''SELECT external_id,acquired_on,direct_account_id,campaign_id,status
                           FROM workspace_leads WHERE workspace_id=%s
                           AND coalesce(acquired_on,created_on) BETWEEN %s AND %s''', (ws, frm, to)).fetchall()
    declaration = conn.execute('''SELECT period_from,period_to,cohort_complete,imported_ids
                                  FROM workspace_lead_imports WHERE workspace_id=%s''', (ws,)).fetchone()
    total = len(rows)
    qualified = sum(r[4] in {'qualified', 'won', 'lost', 'refunded'} for r in rows)
    unresolved = sum(r[4] == 'new' for r in rows)
    declared = bool(declaration and declaration[:3] == (frm, to, True)
                    and set(declaration[3]) == {r[0] for r in rows})
    scope = sorted({r[2] for r in rows})
    valid_accounts = set(scope) <= {a for a, _ in accounts}
    actual, campaigns, spend_reason = spend(conn, ws, frm, to, scope if valid_accounts else [])
    matched = sum(r[2] in scope and (r[3] is None or (r[2], r[3]) in campaigns) for r in rows) if campaigns else 0
    reason = ('no_imported_leads' if not total else 'cohort_completeness_unverified' if not declared
              else 'acquisition_date_missing' if any(r[1] is None for r in rows)
              else 'qualification_incomplete' if unresolved else 'scope_or_period_unmatched' if matched != total
              else spend_reason if spend_reason else 'no_qualified_leads' if not qualified else None)
    amount = None if reason else (Decimal(actual['amount']) / qualified).quantize(CENT)
    qcpl = metric(amount, frm, to, source='yandex_direct+user_input',
                  formula='same acquisition-period account spend / imported qualified leads; completeness declared by user')
    return {'counts': {'total': total, 'qualified': qualified, 'unresolved': unresolved, 'matched': matched},
            'coverage': {'matched_pct': format(Decimal(matched)*100/total, '.2f') if total else None,
                         'qualification_complete': bool(total and not unresolved), 'cohort_complete': declared,
                         'completeness_source': 'user_input'}, 'qcpl': qcpl, 'reason': reason}


def build(conn, ws, today, now, *, period=None, allow_partial=False):
    accounts = selected_accounts(conn, ws)
    plan = conn.execute('SELECT period_from,period_to,amount FROM workspace_budget_plans WHERE workspace_id=%s',
                        (ws,)).fetchone()
    imported = conn.execute('SELECT period_from,period_to FROM workspace_lead_imports WHERE workspace_id=%s',
                            (ws,)).fetchone()
    frm, to = plan[:2] if plan else imported if imported and imported[0] else (today-timedelta(days=7), today-timedelta(days=1))
    if period is not None:
        frm, to = period
        if plan and plan[:2] != period:
            plan = None
    period = {'from': frm.isoformat(), 'to': to.isoformat()}
    actual, _, reason = spend(conn, ws, frm, to, [a for a, _ in accounts], allow_partial=allow_partial)
    variance = None if not plan or actual['amount'] is None else Decimal(actual['amount'])-plan[2]
    budget = {'plan': None if not plan else {'period': period, 'amount': format(plan[2], '.2f'), 'currency': 'RUB'},
              'actual': actual, 'variance': metric(variance, frm, to, source='yandex_direct+user_input',
                                                  formula='actual period spend - user budget', partial=actual['data_status']=='partial'), 'reason': reason}
    quality = lead_quality(conn, ws, frm, to, accounts)
    data_health = health(conn, ws, today, accounts)
    facts = [{'id': 'spent', 'label': 'Расход за период', 'value': actual,
              'detail': 'Только полностью покрытый период и выбранные аккаунты.'},
             {'id': 'qcpl', 'label': 'Стоимость квалифицированного лида', 'value': quality['qcpl'],
              'detail': 'Полнота импорта заявлена пользователем; Rekvero не подтверждает полноту CRM.'}]
    limitations = ['Сводка формируется по запросу; доставка по расписанию не настроена.',
                   'Наличие данных и целей не доказывает корректность учёта или причинный эффект рекламы.']
    if actual['data_status'] == 'partial':
        limitations.append('Данные последних дней предварительные; значения могут уточняться после дозачёта.')
    if quality['reason']:
        limitations.append('qCPL недоступен: ' + LEAD_REASONS.get(quality['reason'], 'проверьте полноту и сопоставимость данных.'))
    return {'period': period, 'ad_accounts': [{'id': f'acc_{a}'} for a, _ in accounts], 'health': data_health,
            'budget': budget, 'lead_quality': quality,
            'summary': {'period': period, 'generated_at': now.isoformat(), 'delivery': 'manual_pull',
                        'facts': facts, 'limitations': limitations}}

