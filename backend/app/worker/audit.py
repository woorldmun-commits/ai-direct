"""Воркер аудита workspace: guard → блокировки → guard ещё раз → состав на data_cutoff → правила по каждому
аккаунту → доказательная цепочка и жизненный цикл рекомендаций. Всё — одна транзакция. К API не обращается.

data_cutoff приходит в задаче и фиксируется до выборки снимков: снимок, появившийся во время аудита, в него не
попадёт. Ключ идемпотентности — task_key: повтор той же задачи возвращает тот же audit_run, без дублей.
Уведомления здесь не отправляются (outbox — следующий срез)."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg.types.json import Jsonb

from app.audit.persist import AccountResult, persist_finding, resolve_disappeared, touch_key
from app.audit.selection import Included, Selection, select_accounts
from app.rules import RULES
from app.rules.domain import AuditSettings, Finding, run
from app.sync.store import load_view
from app.worker.guard import Skip, Task, guard, load_state
from app.worker.locks import audit_exclusive, workspace_shared
from app.worker.sync import Skipped


@dataclass(frozen=True)
class Audited:
    audit_run_id: int


def _existing(conn: psycopg.Connection, workspace_id: int, task_key: str) -> int | None:
    """Только свой workspace: ключ другого — не «тот же аудит», а коллизия (UniqueViolation наружу)."""
    row = conn.execute("SELECT id FROM audit_runs WHERE task_key = %s AND workspace_id = %s",
                       (task_key, workspace_id)).fetchone()
    return row[0] if row else None


def _settings(conn: psycopg.Connection, workspace_id: int) -> tuple[AuditSettings, dict]:
    """Настройки, которые читают правила, — копией в audit_run: их изменение не «перепишет» старый вывод."""
    row = conn.execute("""SELECT target_cpa, avg_check, lead_to_sale_rate, notify_pct_threshold, attribution_model
                          FROM workspace_settings WHERE workspace_id = %s""", (workspace_id,)).fetchone()
    names = ("target_cpa", "avg_check", "lead_to_sale_rate", "notify_pct_threshold", "attribution_model")
    frozen = {n: (str(v) if isinstance(v, Decimal) else v) for n, v in zip(names, row or (None,) * len(names))}
    return AuditSettings(target_cpa=row[0] if row else None), frozen


def _evaluate(conn: psycopg.Connection, workspace_id: int, inc: Included, settings: AuditSettings,
              ran: set[str], skipped: list[dict]) -> AccountResult:
    view = load_view(conn, inc.snapshot_id)
    partial_from = conn.execute("SELECT partial_from FROM snapshots WHERE id = %s", (inc.snapshot_id,)).fetchone()[0]
    result = AccountResult(inc.account_id, inc.snapshot_id, partial_from)
    campaigns = {d.campaign_id for d in view.campaign_days}
    for rule in RULES:
        if not rule.applies(settings):
            continue  # версия не для этих настроек — работает другая версия того же семейства
        ran.add(rule.rule_version)
        if rule.required_sources <= view.sources:
            result.checked.setdefault(rule.family, set()).update(campaigns)
        for out in run(rule, view, settings):
            if isinstance(out, Finding):
                result.findings.append(out)
                result.touched.add(out.issue_key)
                continue
            skipped.append({"account": inc.account_id, "rule": out.rule_version, "reason": out.reason.value,
                            "object_type": out.object_type, "object_id": out.object_id})
            if out.object_id is not None:
                touch_key(result, workspace_id, rule.family, out.object_type, out.object_id)
    return result


def _write(conn: psycopg.Connection, workspace_id: int, task_key: str, release_id: int, sel: Selection) -> int:
    settings, frozen = _settings(conn, workspace_id)
    ran, skipped = set(), []
    results = [_evaluate(conn, workspace_id, inc, settings, ran, skipped) for inc in sel.included]
    audit_run_id = conn.execute(
        """INSERT INTO audit_runs (workspace_id, release_id, kind, task_key, data_cutoff, settings, rules_run,
                                   rules_skipped, excluded_accounts)
           VALUES (%s, %s, 'scheduled', %s, %s, %s, %s, %s, %s) RETURNING id""",
        (workspace_id, release_id, task_key, sel.data_cutoff, Jsonb(frozen), sorted(ran), Jsonb(skipped),
         Jsonb([e.to_json() for e in sel.excluded]))).fetchone()[0]
    for inc in sel.included:
        conn.execute("INSERT INTO audit_run_snapshots (audit_run_id, direct_account_id, snapshot_id) VALUES (%s, %s, %s)",
                     (audit_run_id, inc.account_id, inc.snapshot_id))
    for result in results:
        for f in result.findings:
            persist_finding(conn, audit_run_id, workspace_id, release_id, result, f)
        resolve_disappeared(conn, workspace_id, result)
    return audit_run_id


def run_audit(conn: psycopg.Connection, *, workspace_id: int, task_key: str, data_cutoff: date, release_id: int,
              now: datetime) -> Audited | Skipped:
    assert conn.autocommit, "воркер требует соединение с autocommit=True"
    if (existing := _existing(conn, workspace_id, task_key)) is not None:
        return Audited(existing)
    if isinstance(d := guard(Task.AUDIT, load_state(conn, workspace_id, None, now)), Skip):
        return Skipped(d.reason, d.detail)
    try:
        with conn.transaction():
            workspace_shared(conn, workspace_id)
            audit_exclusive(conn, workspace_id)  # два аудита одного workspace не пишут проблемы одновременно
            if isinstance(d := guard(Task.AUDIT, load_state(conn, workspace_id, None, now)), Skip):
                return Skipped(d.reason, d.detail)
            if (existing := _existing(conn, workspace_id, task_key)) is not None:
                return Audited(existing)
            sel = select_accounts(conn, workspace_id, data_cutoff, now)
            if not sel.included:
                return Skipped("no_snapshots_for_cutoff", data_cutoff.isoformat())
            return Audited(_write(conn, workspace_id, task_key, release_id, sel))
    except psycopg.errors.UniqueViolation:
        if (existing := _existing(conn, workspace_id, task_key)) is None:
            raise
        return Audited(existing)
