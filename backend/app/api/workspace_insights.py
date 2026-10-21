"""Tenant-scoped manual insights; no billing or external advertising writes."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from app.api.active import today_msk
from app.api.deps import Conn, CurrentWorkspace
from app.api.errors import ApiError
from app.insights import lead_import, report

router = APIRouter()


class BudgetPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    period_from: StrictStr
    period_to: StrictStr
    amount: StrictStr


class LeadImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    csv: Annotated[StrictStr, Field(max_length=48000)]
    period_from: StrictStr | None = None
    period_to: StrictStr | None = None
    cohort_complete: StrictBool = False


def _write_role(ws):
    if ws.role not in ('owner', 'admin', 'approver', 'analyst'):
        raise ApiError(403, 'forbidden_role')


def _period(frm, to):
    start, end = lead_import.day(frm), lead_import.day(to)
    if end < start or (end-start).days >= 366:
        raise lead_import.InvalidImport('period_bounds')
    return start, end


def _invalid(exc):
    return ApiError(400, 'invalid_request', str(exc))


@router.get('/workspaces/{workspace_id}/insights')
def insights(conn: Conn, ws: CurrentWorkspace):
    return report.build(conn, ws.id, today_msk(), datetime.now(timezone.utc))


@router.get('/workspaces/{workspace_id}/weekly-report')
def weekly_report(conn: Conn, ws: CurrentWorkspace):
    today = today_msk()
    frm, to = today-timedelta(days=7), today-timedelta(days=1)
    counts = conn.execute('''SELECT e.type,count(*) FROM recommendation_events e
        JOIN recommendations r ON r.id=e.recommendation_id JOIN issues i ON i.id=r.issue_id
        WHERE i.workspace_id=%s AND e.created_at >= %s AND e.created_at < %s
        AND e.type IN ('done','checked','rejected','postponed','measured','measurement_skipped')
        GROUP BY e.type ORDER BY e.type''',
        (ws.id, datetime.combine(frm, datetime.min.time(), ZoneInfo('Europe/Moscow')),
         datetime.combine(today, datetime.min.time(), ZoneInfo('Europe/Moscow')))).fetchall()
    return {'insights': report.build(conn, ws.id, today, datetime.now(timezone.utc), period=(frm,to), allow_partial=True),
            'decisions': [{'type': kind, 'count': count} for kind,count in counts]}


@router.post('/workspaces/{workspace_id}/budget-plan')
def budget_plan(body: BudgetPlan, conn: Conn, ws: CurrentWorkspace):
    _write_role(ws)
    try:
        frm, to = _period(body.period_from, body.period_to)
        amount = lead_import.money(body.amount)
        if amount <= 0:
            raise lead_import.InvalidImport('budget_positive')
    except lead_import.InvalidImport as exc:
        raise _invalid(exc) from None
    conn.execute('SELECT pg_advisory_xact_lock(%s)', (ws.id,))
    conn.execute('''INSERT INTO workspace_budget_plans (workspace_id,period_from,period_to,amount)
                    VALUES (%s,%s,%s,%s) ON CONFLICT (workspace_id) DO UPDATE SET
                    period_from=EXCLUDED.period_from,period_to=EXCLUDED.period_to,
                    amount=EXCLUDED.amount,updated_at=now()''', (ws.id, frm, to, amount))
    return {'period': {'from': frm.isoformat(), 'to': to.isoformat()}, 'amount': format(amount, '.2f'), 'currency': 'RUB'}


@router.post('/workspaces/{workspace_id}/lead-import')
def lead_import_csv(body: LeadImport, conn: Conn, ws: CurrentWorkspace):
    return _import(body, conn, ws)


@router.post('/workspaces/{workspace_id}/lead-import/preview')
def preview_import(body: LeadImport, conn: Conn, ws: CurrentWorkspace):
    return _import(body, conn, ws, preview=True)


def _import(body, conn, ws, *, preview=False):
    _write_role(ws)
    try:
        if (body.period_from is None) != (body.period_to is None) or (body.cohort_complete and body.period_from is None):
            raise lead_import.InvalidImport('cohort_period_required')
        frm, to = _period(body.period_from, body.period_to) if body.period_from is not None else (None, None)
        if to and to >= today_msk():
            raise lead_import.InvalidImport('cohort_period_not_closed')
        rows = lead_import.parse(body.csv, today_msk())
        return lead_import.store(conn, ws.id, rows, body.csv, frm, to, body.cohort_complete, preview=preview)
    except lead_import.InvalidImport as exc:
        raise _invalid(exc) from None

