"""GET /workspaces/{ws}/today — «Сегодня» (API_CONTRACT.md §8, PRODUCT_SPEC.md §5): сколько ≈ (итог без двойного
учёта), сколько проблем, 3 приоритетных действия, что проверено, свежесть данных. Только чтение, только через
CurrentWorkspace (RLS).

Активные рекомендации — открытая проблема, нет решения человека (последнее событие статуса — нет или unpostponed),
текущий вывод (последний seen_again или исходный) — из последнего аудита, в который вошёл кабинет, и кабинет включён
в анализ. По ним — exposure_total@1 (app/audit/exposure.py) на строках снимков этих аудитов; суммы не пересчитываются
здесь и не складываются: всё, что уходит клиенту, — сериализованный Value.

audit_scope и spent — по последнему аудиту workspace: его правила@версии, окно оценки (7 дней до data_cutoff,
rules.domain.windows), кабинеты и кампании со статистикой в окне; spent — их расход (actual, stat_rows уровня кампании).

Поля §8, которых в схеме ещё нет (access, can_save, saved, conversions, recent_actions, changes, counts по статусам),
не отдаются — в контракте они помечены «появится» (API_CONTRACT.md §8); вместо counts по статусам — counts.active."""

from datetime import date, datetime, timezone
from decimal import Decimal

import psycopg
from fastapi import APIRouter

from app.api.deps import Conn, CurrentWorkspace
from app.api.serialize import moment, recommendation_item, value_of
from app.audit.exposure import (ACCOUNT_LEVEL, CAMPAIGN_LEVEL, ExposureFinding, StatUnit, basis_from_meta,
                                exposure_total)
from app.contract import Value
from app.rules.domain import windows

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
       cur.issue_type, f.data_quality, latest.snapshot_id, f.evidence_meta, f.created_at, f.action
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
    """Строки снимков, на которых посчитаны выводы: уровень кампании (расход), уровни объектных выводов и уровни
    единиц из декларированной основы exposure (площадки у вывода уровня кампании)."""
    snapshots = {row[2]: row[13] for row in rows}  # кабинет → снимок его последнего аудита
    units = []
    for account, snapshot in sorted(snapshots.items()):
        mine = [f for f in findings if f.account_id == account]
        levels = sorted({CAMPAIGN_LEVEL} | {f.object_type for f in mine if f.object_type != ACCOUNT_LEVEL}
                        | {f.basis.level for f in mine if f.basis is not None and f.basis.level is not None})
        params = {"snapshot": snapshot, "levels": levels, "from": min(f.lost.period_from for f in mine),
                  "to": max(f.lost.period_to for f in mine)}
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
        rows = conn.execute(f"SELECT status, last_success_at FROM {table} WHERE workspace_id = %s ORDER BY id",
                            (ws,)).fetchall()
        # last_success_at — последний успешный запрос к API по любому подключению источника (null — не было)
        last = max((r[1] for r in rows if r[1] is not None), default=None)
        out[source] = {"status": _status([r[0] for r in rows]), "data_to": data_to.isoformat() if data_to else None,
                       "last_success_at": moment(last)}
    return out


_LAST_AUDIT = """SELECT id, data_cutoff, rules_run, jsonb_array_length(excluded_accounts)
                 FROM audit_runs WHERE workspace_id = %s ORDER BY created_at DESC, id DESC LIMIT 1"""
_AUDITED = """SELECT s.snapshot_id, sn.partial_from FROM audit_run_snapshots s
              JOIN snapshots sn ON sn.id = s.snapshot_id WHERE s.audit_run_id = %s ORDER BY s.snapshot_id"""
_SPENT = """SELECT count(DISTINCT (r.snapshot_id, r.campaign_id)), coalesce(sum(r.cost), 0) FROM stat_rows r
            WHERE r.snapshot_id = ANY(%(snapshots)s) AND r.source = 'yandex_direct' AND r.level = 'campaign'
              AND r.date BETWEEN %(from)s AND %(to)s"""
SPENT_FORMULA = "sum(cost) по кампаниям проверенных кабинетов за период"


def _no_spend(frm: date, to: date) -> Value:
    """Снимков нет — расход неизвестен: unavailable, а не 0."""
    return Value(amount=None, unit="rub", source="yandex_direct", period_from=frm, period_to=to,
                 calculation_type="unavailable", data_status="complete", data_sufficiency="insufficient",
                 snapshot_id=0, unavailable_reason="no_data")


def _scope(conn: psycopg.Connection, ws: int, as_of: date) -> tuple[dict | None, Value]:
    """(audit_scope, spent) последнего аудита workspace. Аудита не было — (None, unavailable)."""
    audit = conn.execute(_LAST_AUDIT, (ws,)).fetchone()
    if audit is None:
        return None, _no_spend(as_of, as_of)
    audit_id, cutoff, rules_run, excluded = audit
    period, _ = windows(cutoff)
    audited = conn.execute(_AUDITED, (audit_id,)).fetchall()
    snapshots = [r[0] for r in audited]
    campaigns, cost = conn.execute(_SPENT, {"snapshots": snapshots, "from": period.date_from,
                                            "to": period.date_to}).fetchone()
    scope = {"rules": sorted(rules_run), "period": {"from": period.date_from.isoformat(),
                                                    "to": period.date_to.isoformat()},
             "ad_accounts": {"checked": len(snapshots), "excluded": excluded}, "campaigns": campaigns}
    if not snapshots:
        return scope, _no_spend(period.date_from, period.date_to)
    partial = any(period.date_to >= partial_from for _, partial_from in audited)
    return scope, Value(amount=Decimal(cost).quantize(Decimal("0.01")), unit="rub", source="yandex_direct",
                        period_from=period.date_from, period_to=period.date_to, calculation_type="actual",
                        data_status="partial" if partial else "complete", data_sufficiency="sufficient",
                        snapshot_id=max(snapshots), formula=SPENT_FORMULA)


def _exposure_json(result) -> dict:
    return {"total": value_of(result.total), "overlap": value_of(result.overlap), "version": result.version,
            "formula": result.formula,
            "components": [{"issue_type": c.issue_type, "amount": value_of(c.amount)} for c in result.components],
            "coverage": {"included": result.coverage.included, "unavailable": result.coverage.unavailable}}


@router.get("/workspaces/{workspace_id}/today")
def today(conn: Conn, ws: CurrentWorkspace):
    rows = conn.execute(_ACTIVE, {"ws": ws.id}).fetchall()
    findings = [ExposureFinding(row[2], row[11], row[4], row[5], Value.from_stored(row[7]), basis_from_meta(row[14]))
                for row in rows]
    last_audit_at, cutoff = conn.execute("""SELECT max(created_at), max(data_cutoff) FROM audit_runs
                                            WHERE workspace_id = %s""", (ws.id,)).fetchone()
    as_of: date = cutoff or datetime.now(timezone.utc).date()
    result = exposure_total(findings, _units(conn, rows, findings) if rows else [], as_of=as_of)
    top = [recommendation_item(*row[:11], computed_at=row[15], action_raw=row[16], meta=row[14])
           for row in sorted(rows, key=_priority)[:TOP_LIMIT]]
    partial = any(f.lost.data_status == "partial" for f in findings)
    scope, spent = _scope(conn, ws.id, as_of)
    return {"last_audit_at": moment(last_audit_at), "audit_scope": scope, "spent": value_of(spent),
            "exposure": _exposure_json(result), "counts": {"active": len(rows)}, "top": top,
            "data_freshness": _freshness(conn, ws.id), "data_status": "partial" if partial else "complete"}
