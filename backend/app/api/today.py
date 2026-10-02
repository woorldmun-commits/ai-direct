"""GET /workspaces/{ws}/today — «Сегодня» (API_CONTRACT.md §8, PRODUCT_SPEC.md §5): сколько ≈ (итог без двойного
учёта), сколько проблем, 3 приоритетных действия, свежесть данных. Только чтение, только через CurrentWorkspace (RLS).

Активные рекомендации — открытая проблема, нет решения человека (последнее событие статуса — нет или unpostponed),
текущий вывод (последний seen_again или исходный) — из последнего аудита, в который вошёл кабинет, и кабинет включён
в анализ. По ним — exposure_total@1 (app/audit/exposure.py) на строках снимков этих аудитов; суммы не пересчитываются
здесь и не складываются: всё, что уходит клиенту, — сериализованный Value.

Поля, которых в схеме ещё нет (access, spent, can_save, saved, conversions, recent_actions, changes) или чьё
вычисление не определено (counts по шести статусам), не отдаются: вместо counts по статусам — counts.active."""

from datetime import date, datetime, timezone
from decimal import Decimal

import psycopg
from fastapi import APIRouter

from app.api.deps import Conn, CurrentWorkspace
from app.api.serialize import moment, recommendation_item, value_of
from app.audit.exposure import ACCOUNT_LEVEL, CAMPAIGN_LEVEL, ExposureFinding, StatUnit, exposure_total
from app.contract import Value

router = APIRouter()

TOP_LIMIT = 3
_LEVEL_RANK = {"change": 0, "review": 1, "inspect_only": 2}   # приоритет: уровень действия по убыванию воздействия
_QUALITY_RANK = {"high": 0, "medium": 1, "low": 2}            # затем exposure, затем уверенность (data_quality)

_ACTIVE = """
WITH latest AS (  -- последний аудит, в который вошёл кабинет, и его снимок
  SELECT DISTINCT ON (s.direct_account_id) s.direct_account_id, s.audit_run_id, s.snapshot_id
  FROM audit_run_snapshots s JOIN audit_runs a ON a.id = s.audit_run_id
  WHERE a.workspace_id = %(ws)s
  ORDER BY s.direct_account_id, a.created_at DESC, a.id DESC
), cur AS (
  SELECT r.id, r.created_at, i.direct_account_id, i.issue_type, i.object_type, i.object_id,
         coalesce((SELECT e.finding_id FROM recommendation_events e
                   WHERE e.recommendation_id = r.id AND e.type = 'seen_again' ORDER BY e.id DESC LIMIT 1),
                  r.finding_id) AS finding_id,
         (SELECT e.type FROM recommendation_events e
          WHERE e.recommendation_id = r.id AND e.type NOT IN ('seen_again', 'measurement_skipped')
          ORDER BY e.id DESC LIMIT 1) AS decided,
         (SELECT max(e.created_at) FROM recommendation_events e WHERE e.recommendation_id = r.id) AS last_event_at
  FROM recommendations r JOIN issues i ON i.id = r.issue_id
  WHERE i.workspace_id = %(ws)s AND i.closed_at IS NULL
)
SELECT cur.id, cur.finding_id, cur.direct_account_id, coalesce(da.client_login, dc.yandex_login),
       cur.object_type, cur.object_id, f.action_level, f.lost, f.recoverable, cur.created_at,
       greatest(cur.created_at, f.created_at, cur.last_event_at),
       cur.issue_type, f.data_quality, latest.snapshot_id
FROM cur
JOIN findings f ON f.id = cur.finding_id
JOIN latest ON latest.direct_account_id = cur.direct_account_id AND latest.audit_run_id = f.audit_run_id
JOIN direct_accounts da ON da.id = cur.direct_account_id AND da.is_selected
JOIN direct_connections dc ON dc.id = da.direct_connection_id
WHERE cur.decided IS NULL OR cur.decided = 'unpostponed'
ORDER BY cur.id
"""

_UNITS = """
SELECT r.campaign_id, r.level, r.object_id, r.date, r.cost FROM stat_rows r
WHERE r.snapshot_id = %(snapshot)s AND r.source = 'yandex_direct' AND r.level = ANY(%(levels)s)
  AND r.date BETWEEN %(from)s AND %(to)s
"""


def _units(conn: psycopg.Connection, rows: list[tuple], findings: list[ExposureFinding]) -> list[StatUnit]:
    """Строки снимков, на которых посчитаны выводы: уровень кампании (расход) и уровни объектных выводов."""
    snapshots = {row[2]: row[13] for row in rows}  # кабинет → снимок его последнего аудита
    units = []
    for account, snapshot in sorted(snapshots.items()):
        mine = [f.lost for f in findings if f.account_id == account]
        levels = sorted({CAMPAIGN_LEVEL} | {f.object_type for f in findings
                                             if f.account_id == account and f.object_type != ACCOUNT_LEVEL})
        params = {"snapshot": snapshot, "levels": levels, "from": min(v.period_from for v in mine),
                  "to": max(v.period_to for v in mine)}
        units += [StatUnit(account, *r) for r in conn.execute(_UNITS, params).fetchall()]
    return units


def _priority(row: tuple) -> tuple:
    amount = row[7].get("amount")
    return (_LEVEL_RANK.get(row[6], len(_LEVEL_RANK)), amount is None, -Decimal(amount) if amount else Decimal(0),
            _QUALITY_RANK.get(row[12], len(_QUALITY_RANK)), row[0])


def _status(statuses: list[str]) -> str | None:
    """Статус источника по его подключениям: нет подключений — null; все connected — connected; иначе — статус
    первого неисправного (по id), чтобы UI показал конкретное действие."""
    if not statuses:
        return None
    return next((s for s in statuses if s != "connected"), "connected")


def _freshness(conn: psycopg.Connection, ws: int) -> dict:
    snap_at, direct_to, metrika_to = conn.execute(
        """SELECT max(sealed_at), max(period_to), max(period_to) FILTER (WHERE 'yandex_metrika' = ANY (sources))
           FROM snapshots WHERE workspace_id = %s AND status = 'complete'""", (ws,)).fetchone()
    out = {"last_snapshot_at": moment(snap_at)}
    for source, table, data_to in (("yandex_direct", "direct_connections", direct_to),
                                   ("yandex_metrika", "metrika_connections", metrika_to)):
        statuses = [r[0] for r in conn.execute(f"SELECT status FROM {table} WHERE workspace_id = %s ORDER BY id",
                                               (ws,)).fetchall()]
        out[source] = {"status": _status(statuses), "data_to": data_to.isoformat() if data_to else None}
    return out


def _exposure_json(result) -> dict:
    return {"total": value_of(result.total), "overlap": value_of(result.overlap), "version": result.version,
            "formula": result.formula,
            "components": [{"issue_type": c.issue_type, "amount": value_of(c.amount)} for c in result.components],
            "coverage": {"included": result.coverage.included, "unavailable": result.coverage.unavailable}}


@router.get("/workspaces/{workspace_id}/today")
def today(conn: Conn, ws: CurrentWorkspace):
    rows = conn.execute(_ACTIVE, {"ws": ws.id}).fetchall()
    findings = [ExposureFinding(row[2], row[11], row[4], row[5], Value.model_validate(row[7])) for row in rows]
    last_audit_at, cutoff = conn.execute("""SELECT max(created_at), max(data_cutoff) FROM audit_runs
                                            WHERE workspace_id = %s""", (ws.id,)).fetchone()
    as_of: date = cutoff or datetime.now(timezone.utc).date()
    result = exposure_total(findings, _units(conn, rows, findings) if rows else [], as_of=as_of)
    top = [recommendation_item(*row[:11]) for row in sorted(rows, key=_priority)[:TOP_LIMIT]]
    partial = any(f.lost.data_status == "partial" for f in findings)
    return {"last_audit_at": moment(last_audit_at), "exposure": _exposure_json(result),
            "counts": {"active": len(rows)}, "top": top, "data_freshness": _freshness(conn, ws.id),
            "data_status": "partial" if partial else "complete"}
