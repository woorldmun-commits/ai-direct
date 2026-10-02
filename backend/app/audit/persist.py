"""Результаты правил → доказательная цепочка и жизненный цикл рекомендаций (DATA_MODEL.md §4, §8.3).

Вывод по новой проблеме → issue + finding + explanation + recommendation.
Вывод по открытой проблеме → finding + explanation + событие seen_again (рекомендация та же, действие пересчитано).
Проблема исчезла → resolved, но только если её действительно проверили: аккаунт в аудите, версия семейства правила
вычислялась, объект есть в снимке и по нему нет «недостаточно данных». Выполненную (done) рекомендацию
resolved не закрывает — её закроет замер (measured)."""

from dataclasses import dataclass, field
from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from app.audit.exposure import basis_meta
from app.audit.policy import decide
from app.audit.templates import explain
from app.audit.values import to_value
from app.rules.domain import Finding, issue_key
from app.worker.outbox import emit


@dataclass
class AccountResult:
    """Что аудит узнал по одному аккаунту: выводы, проверенные объекты по семействам, «тронутые» ключи проблем."""
    account_id: int
    snapshot_id: int
    partial_from: date
    findings: list[Finding] = field(default_factory=list)
    checked: dict[str, set[int]] = field(default_factory=dict)  # семейство → id кампаний, которые правило проверило
    touched: set[bytes] = field(default_factory=set)            # ключи с выводом или «недостаточно данных»


def _finding_row(f: Finding, snapshot_id: int, partial_from: date) -> tuple:
    def value(fact):
        return to_value(fact, snapshot_id, partial_from, f.rule_version).model_dump(mode="json")
    meta = {**f.evidence_meta, "reason_code": f.reason_code, "metric": f.metric, "reference_type": f.reference_type,
            "actual": str(f.actual), "reference": str(f.reference), "delta_pct": str(f.delta_pct),
            **basis_meta(f.exposure_basis)}  # основа exposure — для итога без двойного учёта (api/today.py)
    d = decide(f)
    return (f.rule_version, Jsonb(value(f.lost)), Jsonb(value(f.recoverable)), f.current_data_quality,
            Jsonb({k: value(x) for k, x in f.evidence.items()}), Jsonb(meta), Jsonb(dict(f.action)),
            d.version, d.candidate_level, d.level, list(d.reasons))


def _open_issue(conn: psycopg.Connection, workspace_id: int, account_id: int, f: Finding) -> int:
    row = conn.execute("SELECT id FROM issues WHERE issue_key = %s AND closed_at IS NULL", (f.issue_key,)).fetchone()
    if row:
        return row[0]
    return conn.execute("""INSERT INTO issues (workspace_id, direct_account_id, issue_key, issue_type, object_type,
                                               object_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                        (workspace_id, account_id, f.issue_key, f.issue_type, f.object_type, f.object_id)).fetchone()[0]


def persist_finding(conn: psycopg.Connection, audit_run_id: int, workspace_id: int, release_id: int,
                    result: AccountResult, f: Finding) -> None:
    issue_id = _open_issue(conn, workspace_id, result.account_id, f)
    finding_id = conn.execute(
        """INSERT INTO findings (audit_run_id, issue_id, rule_version, lost, recoverable, data_quality, evidence,
                                 evidence_meta, action, safety_policy, candidate_level, action_level, policy_reasons)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (audit_run_id, issue_id, *_finding_row(f, result.snapshot_id, result.partial_from))).fetchone()[0]
    explanation_id = conn.execute("""INSERT INTO explanations (finding_id, source, text, release_id)
                                     VALUES (%s, 'template', %s, %s) RETURNING id""",
                                  (finding_id, explain(f, decide(f)), release_id)).fetchone()[0]
    rec = conn.execute("SELECT id FROM recommendations WHERE issue_id = %s", (issue_id,)).fetchone()
    payload = {"issue_id": issue_id, "finding_id": finding_id, "rule_version": f.rule_version}
    if rec is None:
        rec_id = conn.execute("""INSERT INTO recommendations (issue_id, finding_id, explanation_id)
                                 VALUES (%s, %s, %s) RETURNING id""", (issue_id, finding_id, explanation_id)).fetchone()[0]
        emit(conn, workspace_id, "recommendation_created", "recommendation", rec_id, payload)
    else:
        conn.execute("""INSERT INTO recommendation_events (recommendation_id, type, finding_id, explanation_id)
                        VALUES (%s, 'seen_again', %s, %s)""", (rec[0], finding_id, explanation_id))
        emit(conn, workspace_id, "recommendation_seen_again", "recommendation", rec[0], payload)


def _current_status(conn: psycopg.Connection, recommendation_id: int) -> str:
    row = conn.execute("""SELECT type FROM recommendation_events WHERE recommendation_id = %s
                          AND type NOT IN ('seen_again', 'measurement_skipped')
                          ORDER BY id DESC LIMIT 1""", (recommendation_id,)).fetchone()
    return row[0] if row else "new"


def resolve_disappeared(conn: psycopg.Connection, workspace_id: int, result: AccountResult) -> None:
    for family, campaigns in result.checked.items():
        open_issues = conn.execute("""SELECT i.id, i.issue_key, i.object_id, r.id FROM issues i
                                      LEFT JOIN recommendations r ON r.issue_id = i.id
                                      WHERE i.workspace_id = %s AND i.direct_account_id = %s AND i.issue_type = %s
                                        AND i.object_type = 'campaign' AND i.closed_at IS NULL""",
                                   (workspace_id, result.account_id, family)).fetchall()
        for issue_id, key, object_id, rec_id in open_issues:
            if bytes(key) in result.touched or object_id not in campaigns:
                continue  # подтвердилась, не хватило данных или объект не проверялся — не «исчезла»
            if rec_id is not None and _current_status(conn, rec_id) == "done":
                continue  # ждёт замера: закроет measured, не resolved
            if rec_id is not None:
                conn.execute("INSERT INTO recommendation_events (recommendation_id, type) VALUES (%s, 'resolved')",
                             (rec_id,))
                emit(conn, workspace_id, "recommendation_resolved", "recommendation", rec_id, {"issue_id": issue_id})
            conn.execute("UPDATE issues SET closed_at = now(), close_reason = 'resolved' WHERE id = %s", (issue_id,))


def touch_key(result: AccountResult, workspace_id: int, family: str, object_type: str, object_id: int) -> None:
    result.touched.add(issue_key(workspace_id, result.account_id, family, object_type, object_id))
