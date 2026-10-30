"""Linear budget scenario using final covered days. No seasonality or platform budget writes."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

CENT=Decimal('.01')


def calculate(plan,spent,start,end,observed):
    if not start<=observed<=end or plan<=0 or spent<0:
        raise ValueError('Invalid pacing inputs')
    total=(end-start).days+1
    days=(observed-start).days+1
    expected=plan*days/total
    projected=spent*total/days
    left=total-days
    status=('complete' if not left else 'exceeded' if spent>plan else
            'ahead' if spent>expected*Decimal('1.1') else 'behind' if spent<expected*Decimal('.9') else 'on_track')
    def money(value):
        return format(value.quantize(CENT, rounding=ROUND_HALF_UP), '.2f')
    return {'status':status,'days_observed':days,'days_total':total,'observed_to':observed.isoformat(),
        'spent':money(spent),'expected_to_date':money(expected),'projected_total':money(projected),
        'remaining_daily':money(max(plan-spent,Decimal('0'))/left) if left else None,
        'deviation_pct':format(((spent/expected-1)*100).quantize(CENT,rounding=ROUND_HALF_UP),'.2f')}


def build(conn,ws,plan,accounts,today,now,spend):
    base={'available':False,'reason':'no_plan','method':'linear_budget_pacing@1'}
    if not plan:
        return base
    start,end,amount=plan
    if not accounts or any(status!='connected' for _,status in accounts):
        return dict(base,reason='connection_unavailable')
    snaps=conn.execute('''SELECT DISTINCT ON (r.direct_account_id) r.direct_account_id,s.partial_from,s.sealed_at
        FROM snapshots s JOIN sync_runs r ON r.id=s.sync_run_id WHERE s.workspace_id=%s
        AND s.status='complete' AND r.direct_account_id=ANY(%s)
        ORDER BY r.direct_account_id,s.sealed_at DESC,s.id DESC''',(ws,[a for a,_ in accounts])).fetchall()
    if len(snaps)!=len(accounts):
        return dict(base,reason='coverage_missing')
    if any(now-sealed>timedelta(hours=72) for _,_,sealed in snaps):
        return dict(base,reason='stale_data')
    observed=min(end,today-timedelta(days=1),*(partial-timedelta(days=1) for _,partial,_ in snaps))
    if observed<start:
        return dict(base,reason='no_final_days')
    actual,_,reason=spend(conn,ws,start,observed,[a for a,_ in accounts])
    if reason or actual['amount'] is None:
        return dict(base,reason=reason or 'coverage_missing')
    return dict(calculate(amount,Decimal(actual['amount']),start,end,observed),available=True,
        reason=None,method=base['method'],period={'from':start.isoformat(),'to':end.isoformat()},
        plan=format(amount,'.2f'),actual=actual,
        limitations=['Линейный сценарий при сохранении среднего расхода; сезонность и расписание не учитываются.',
            'Предварительные дни исключены. Рекомендуемый остаток относится к дням после даты окончательных данных.',
            'Отклонение более 10% — сигнал проверки плана, а не вывод об эффективности. Реклама не изменяется.'])
