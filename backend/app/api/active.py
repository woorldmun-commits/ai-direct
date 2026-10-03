"""Активные рекомендации — одно определение для «Сегодня» и «Рекомендаций» (API_CONTRACT.md §5, §8).

Активна рекомендация, если одновременно:
1. проблема открыта (issues.closed_at IS NULL);
2. её кабинет выбран (is_selected) и вошёл в ПОСЛЕДНИЙ аудит workspace — кабинет, исключённый из него (нет доступа,
   нет снимка на cutoff), в итог и счётчики не входит, даже если более старый аудит его видел;
3. последний аудит её проверил: текущий вывод (последний seen_again или исходный) — из этого аудита, ЛИБО аудит
   удержал её через «недостаточно данных» (rules_skipped по её кабинету и семейству: объект проблемы или всё
   правило). Удержанная — активна, но `data_sufficiency = insufficient`: её exposure и can_save — unavailable с
   причиной, в итог exposure не входят (coverage.unavailable + 1), действие — «проверить» (inspect_only);
4. нет решения человека: последнее событие статуса — нет или unpostponed; postponed — не активна до даты until
   (по МСК), после неё — снова активна.

status (v1.0, из существующих событий): new · postponed · rejected · applied (done / checked / measured).
Событий просмотра и принятия ещё нет (неделя 4), поэтому requires_decision / accepted не выдаются."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import psycopg

from app.audit.exposure import (ACCOUNT_LEVEL, CAMPAIGN_LEVEL, ExposureFinding, ExposureTotal, StatUnit,
                                basis_from_meta, exposure_total)
from app.contract import Value
from app.rules import RULES
from app.rules.domain import UNAVAILABLE_REASON_OF, Reason, windows

MSK = timezone(timedelta(hours=3), "MSK")  # пояс данных Директа (как DATA_TIMEZONE воркеров; без перехода на летнее)
FAMILY_OF = {r.rule_version: r.family for r in RULES}
_REASONS = {r.value: r for r in Reason}

_CANDIDATES = """
WITH last AS (
  SELECT id, data_cutoff, rules_skipped FROM audit_runs WHERE workspace_id = %(ws)s
  ORDER BY created_at DESC, id DESC LIMIT 1
), included AS (
  SELECT s.direct_account_id, s.snapshot_id, sn.partial_from FROM audit_run_snapshots s
  JOIN last ON last.id = s.audit_run_id JOIN snapshots sn ON sn.id = s.snapshot_id
), cur AS (
  SELECT r.id, r.created_at, i.direct_account_id, i.issue_type, i.object_type, i.object_id,
         coalesce((SELECT e.finding_id FROM recommendation_events e
                   WHERE e.recommendation_id = r.id AND e.type = 'seen_again' ORDER BY e.id DESC LIMIT 1),
                  r.finding_id) AS finding_id,
         (SELECT max(e.created_at) FROM recommendation_events e WHERE e.recommendation_id = r.id) AS last_event_at
  FROM recommendations r JOIN issues i ON i.id = r.issue_id
  WHERE i.workspace_id = %(ws)s AND i.closed_at IS NULL
    AND (%(account)s::bigint IS NULL OR i.direct_account_id = %(account)s::bigint)
)
SELECT cur.id, cur.finding_id, cur.direct_account_id, coalesce(da.client_login, dc.yandex_login), cur.issue_type,
       cur.object_type, cur.object_id, f.action_level, f.lost, f.recoverable, f.data_quality, f.evidence_meta,
       f.action, f.created_at, cur.created_at, greatest(cur.created_at, f.created_at, cur.last_event_at),
       f.audit_run_id = last.id, last.data_cutoff, last.rules_skipped, included.snapshot_id, included.partial_from,
       d.type, d.payload->>'until'
FROM cur
CROSS JOIN last
JOIN included ON included.direct_account_id = cur.direct_account_id
JOIN findings f ON f.id = cur.finding_id
JOIN direct_accounts da ON da.id = cur.direct_account_id AND da.is_selected
JOIN direct_connections dc ON dc.id = da.direct_connection_id
LEFT JOIN LATERAL (SELECT e.type, e.payload FROM recommendation_events e
                   WHERE e.recommendation_id = cur.id AND e.type NOT IN ('seen_again', 'measurement_skipped')
                   ORDER BY e.id DESC LIMIT 1) d ON true
ORDER BY cur.id
"""


@dataclass(frozen=True)
class Card:
    """Активная рекомендация в том виде, в каком её сериализует API (числа — как сохранил аудит)."""
    rec_id: int
    finding_id: int
    account_id: int
    login: str | None
    issue_type: str
    object_type: str
    object_id: int
    action_level: str
    lost: Value
    recoverable: Value
    data_quality: str
    meta: dict
    action_raw: dict
    computed_at: datetime
    created_at: datetime
    updated_at: datetime
    snapshot_id: int
    status: str
    insufficient: bool  # удержана «недостаточно данных» последнего аудита


def today_msk(now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(MSK).date()


def status_of(decided: str | None, until: str | None, today: date) -> str:
    """Статус v1.0 из последнего события решения (DATA_MODEL.md §8.3)."""
    if decided in (None, "unpostponed"):
        return "new"
    if decided == "postponed":
        return "postponed" if until is None or date.fromisoformat(until[:10]) > today else "new"
    if decided == "rejected":
        return "rejected"
    if decided in ("done", "checked", "measured"):
        return "applied"
    return "new"  # resolved закрывает проблему — сюда не доходит


def _held(skipped: list, account: int, issue_type: str, object_type: str, object_id: int) -> dict | None:
    """«Недостаточно данных» последнего аудита по этой проблеме: по её объекту или по всему правилу кабинета."""
    for s in skipped or ():
        if s.get("account") != account or FAMILY_OF.get(s.get("rule"), str(s.get("rule")).split("@")[0]) != issue_type:
            continue
        if s.get("object_id") is None or (s.get("object_type"), s.get("object_id")) == (object_type, object_id):
            return s
    return None


def _unavailable(like: Value, held: dict, cutoff: date, snapshot_id: int, partial_from: date | None) -> Value:
    window, _ = windows(cutoff)
    reason = UNAVAILABLE_REASON_OF.get(_REASONS.get(held.get("reason")), "no_data")
    return Value(amount=None, unit=like.unit, source=like.source, period_from=window.date_from,
                 period_to=window.date_to, calculation_type="unavailable",
                 data_status="partial" if partial_from is None or window.date_to >= partial_from else "complete",
                 data_sufficiency="insufficient", snapshot_id=snapshot_id, rule_version=held.get("rule"),
                 unavailable_reason=reason)


def active_cards(conn: psycopg.Connection, ws: int, account: int | None = None,
                 today: date | None = None) -> list[Card]:
    today = today or today_msk()
    cards = []
    for row in conn.execute(_CANDIDATES, {"ws": ws, "account": account}).fetchall():
        (rec, finding, acc, login, issue_type, object_type, object_id, level, lost, recoverable, quality, meta,
         action_raw, computed_at, created_at, updated_at, current, cutoff, skipped, snapshot, partial_from,
         decided, until) = row
        status = status_of(decided, until, today)
        if status != "new":
            continue
        lost_v, recoverable_v = Value.from_stored(lost), Value.from_stored(recoverable)
        insufficient = False
        if not current:
            held = _held(skipped, acc, issue_type, object_type, object_id)
            if held is None:
                continue  # последний аудит её не проверил — не «активная рекомендация последнего аудита»
            insufficient, level = True, "inspect_only"
            lost_v = _unavailable(lost_v, held, cutoff, snapshot, partial_from)
            recoverable_v = _unavailable(recoverable_v, held, cutoff, snapshot, partial_from)
        cards.append(Card(rec, finding, acc, login, issue_type, object_type, object_id, level, lost_v, recoverable_v,
                          quality, meta or {}, action_raw or {}, computed_at, created_at, updated_at, snapshot,
                          status, insufficient))
    return cards


_UNITS = """
SELECT r.campaign_id, r.level, r.object_id, r.date, r.cost FROM stat_rows r
WHERE r.snapshot_id = %(snapshot)s AND r.source = 'yandex_direct' AND r.level = ANY(%(levels)s)
  AND r.date BETWEEN %(from)s AND %(to)s
"""


def _units(conn: psycopg.Connection, cards: list[Card], findings: list[ExposureFinding]) -> list[StatUnit]:
    """Строки снимков, на которых посчитаны выводы: уровень кампании (расход), уровни объектных выводов и уровни
    единиц из декларированной основы exposure (площадки у вывода уровня кампании)."""
    snapshots = {c.account_id: c.snapshot_id for c in cards}  # кабинет → снимок последнего аудита
    units = []
    for account, snapshot in sorted(snapshots.items()):
        mine = [f for f in findings if f.account_id == account]
        levels = sorted({CAMPAIGN_LEVEL} | {f.object_type for f in mine if f.object_type != ACCOUNT_LEVEL}
                        | {f.basis.level for f in mine if f.basis is not None and f.basis.level is not None})
        params = {"snapshot": snapshot, "levels": levels, "from": min(f.lost.period_from for f in mine),
                  "to": max(f.lost.period_to for f in mine)}
        units += [StatUnit(account, *r) for r in conn.execute(_UNITS, params).fetchall()]
    return units


def with_exposure(conn: psycopg.Connection, cards: list[Card], as_of: date) -> tuple[ExposureTotal, dict[int, Value]]:
    """exposure_total@1 по всем активным карточкам и overlap каждой (id рекомендации → Value)."""
    findings = [ExposureFinding(c.account_id, c.issue_type, c.object_type, c.object_id, c.lost,
                                basis_from_meta(c.meta), ref=c.rec_id) for c in cards]
    result = exposure_total(findings, _units(conn, cards, findings) if cards else [], as_of=as_of)
    return result, {c.ref: c.overlap for c in result.cards}
