"""Целостность Issue ↔ Finding ↔ Recommendation ↔ Event ↔ Result — реляционно, силами БД.

Issue A ── Finding A ── Recommendation A
Issue B ── Finding B ── Recommendation B
Любая ссылка из A в B должна отвергаться базой, а не кодом."""

import psycopg
import pytest
from psycopg.types.json import Jsonb

from test_schema import EVENT_AT, EXECUTED, chain, chain_factory_second_finding, one, value  # noqa: F401 — chain: фикстура


def add_finding(rw, chain, issue, change_pct):
    """Новая синхронизация и аудит той же проблемы: finding + объяснение. Возвращает (finding, explanation)."""
    sync = one(rw, """INSERT INTO sync_runs (workspace_id, direct_account_id, kind, status, finished_at)
                      VALUES (%s, %s, 'scheduled', 'succeeded', now()) RETURNING id""", chain["ws"], chain["account"])
    snap = one(rw, """INSERT INTO snapshots (workspace_id, sync_run_id, release_id, period_from, period_to,
                        data_until, partial_from, sources)
                      VALUES (%s, %s, %s, '2026-08-25', '2026-09-30', now(), '2026-09-28', '{yandex_direct}')
                      RETURNING id""", chain["ws"], sync, chain["release"])
    rw.execute("UPDATE snapshots SET status = 'complete', sealed_at = now() WHERE id = %s", (snap,))
    audit = one(rw, """INSERT INTO audit_runs (workspace_id, release_id, kind, task_key, data_cutoff, settings,
                                                rules_run)
                       VALUES (%s, %s, 'scheduled', gen_random_uuid()::text, '2026-09-30', '{}', '{high_cpa_target@1}')
                       RETURNING id""", chain["ws"], chain["release"])
    finding = one(rw, """INSERT INTO findings (audit_run_id, issue_id, rule_version, lost, recoverable, data_quality, evidence, action, safety_policy, candidate_level, action_level)
                         VALUES (%s, %s, 'high_cpa_target@1', %s, %s, 'medium', '{}', %s, 'safety_policy@1', 'review', 'review') RETURNING id""",
                  audit, issue, Jsonb(value()), Jsonb(value()), Jsonb({"type": "decrease_bid", "change_pct": change_pct}))
    expl = one(rw, "INSERT INTO explanations (finding_id, source, text, release_id) VALUES (%s, 'template', 't', %s) RETURNING id",
               finding, chain["release"])
    return finding, expl


def event(rw, rec, type_, actor=None, finding=None, explanation=None, result=None):
    done = type_ == "done"
    return one(rw, """INSERT INTO recommendation_events (recommendation_id, type, actor_user_id, finding_id,
                                                         explanation_id, result_id, execution_date, created_at)
                      VALUES (%s, %s, %s, %s, %s, %s, %s, coalesce(%s, now())) RETURNING id""",
               rec, type_, actor, finding, explanation, result, EXECUTED if done else None, EVENT_AT if done else None)


def result(rw, chain, rec, finding):
    return one(rw, """INSERT INTO recommendation_results (recommendation_id, finding_id, snapshot_id, release_id,
                        before, after, verdict)
                      VALUES (%s, %s, %s, %s, '{}', '{}', 'no_effect') RETURNING id""",
               rec, finding, chain["snapshot"], chain["release"])


@pytest.fixture
def two(rw, chain):
    """Две независимые проблемы A и B, у каждой своя рекомендация."""
    b = chain_factory_second_finding(rw, chain)
    expl_b = one(rw, "INSERT INTO explanations (finding_id, source, text, release_id) VALUES (%s, 'template', 't', %s) RETURNING id",
                 b["finding"], chain["release"])
    rec_b = one(rw, "INSERT INTO recommendations (issue_id, finding_id, explanation_id) VALUES (%s, %s, %s) RETURNING id",
                b["issue"], b["finding"], expl_b)
    return {"a": {"issue": chain["issue"], "finding": chain["finding"], "expl": chain["explanation"], "rec": chain["rec"]},
            "b": {"issue": b["issue"], "finding": b["finding"], "expl": expl_b, "rec": rec_b},
            "user": chain["user"]}


# --- Чужие ссылки отвергаются ----------------------------------------------------------------------

def test_recommendation_cannot_use_finding_of_other_issue(rw, chain):
    """Рекомендация проблемы C не может опираться на вывод проблемы B."""
    b = chain_factory_second_finding(rw, chain)
    expl_b = one(rw, "INSERT INTO explanations (finding_id, source, text, release_id) VALUES (%s, 'template', 't', %s) RETURNING id",
                 b["finding"], chain["release"])
    issue_c = one(rw, """INSERT INTO issues (workspace_id, direct_account_id, issue_key, issue_type, object_type, object_id)
                         VALUES (%s, %s, %s, 'high_cpa', 'campaign', 999) RETURNING id""",
                  chain["ws"], chain["account"], b"" * 31 + bytes([chain["ws"] % 256]))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        rw.execute("INSERT INTO recommendations (issue_id, finding_id, explanation_id) VALUES (%s, %s, %s)",
                   (issue_c, b["finding"], expl_b))


def test_done_with_finding_of_other_issue_is_rejected(rw, two):
    """Самый опасный случай: Recommendation A → done(Finding B). Отвергают два слоя: триггер «показан ли вывод» и FK."""
    with pytest.raises(psycopg.IntegrityError):
        event(rw, two["a"]["rec"], "done", actor=two["user"], finding=two["b"]["finding"])


def test_seen_again_with_finding_of_other_issue_is_rejected(rw, two):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        event(rw, two["a"]["rec"], "seen_again", finding=two["b"]["finding"], explanation=two["b"]["expl"])


def test_seen_again_explanation_must_belong_to_its_finding(rw, chain, two):
    finding2, _ = add_finding(rw, chain, two["a"]["issue"], -25)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):  # объяснение от старого вывода к новому
        event(rw, two["a"]["rec"], "seen_again", finding=finding2, explanation=two["a"]["expl"])


def test_issue_id_is_taken_from_recommendation_not_from_client(rw, two):
    """issue_id события нельзя подменить: триггер перезаписывает его из рекомендации."""
    ev = one(rw, """INSERT INTO recommendation_events (recommendation_id, issue_id, type, actor_user_id, finding_id,
                                                       execution_date, created_at)
                    VALUES (%s, %s, 'done', %s, %s, %s, %s) RETURNING issue_id""",
             two["a"]["rec"], two["b"]["issue"], two["user"], two["a"]["finding"], EXECUTED, EVENT_AT)
    assert ev == two["a"]["issue"]


def test_done_on_finding_never_shown_is_rejected(rw, chain, two):
    """Тот же issue, но вывод не был показан через seen_again — выполнить его нельзя."""
    unseen, _ = add_finding(rw, chain, two["a"]["issue"], -40)
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        event(rw, two["a"]["rec"], "done", actor=two["user"], finding=unseen)


def test_result_of_other_issue_finding_is_rejected(rw, chain, two):
    event(rw, two["a"]["rec"], "done", actor=two["user"], finding=two["a"]["finding"])
    with pytest.raises(psycopg.IntegrityError):
        result(rw, chain, two["a"]["rec"], two["b"]["finding"])


def test_result_without_done_is_rejected(rw, chain, two):
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        result(rw, chain, two["a"]["rec"], two["a"]["finding"])


def test_measured_must_point_to_own_result(rw, chain, two):
    a, b = two["a"], two["b"]
    event(rw, a["rec"], "done", actor=two["user"], finding=a["finding"])
    event(rw, b["rec"], "done", actor=two["user"], finding=b["finding"])
    res_b = result(rw, chain, b["rec"], b["finding"])
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        event(rw, a["rec"], "measured", finding=a["finding"], result=res_b)


# --- Пересчёт −15% → −25% --------------------------------------------------------------------------

def test_recalculation_chain_done_and_measured_use_latest_version(rw, chain):
    """audit #1 → −15% · audit #2 → seen_again −25% · done → −25% · measurement → −25%."""
    rec, issue, user = chain["rec"], chain["issue"], chain["user"]
    finding15 = chain["finding"]  # audit #1: исходный вывод рекомендации
    finding25, expl25 = add_finding(rw, chain, issue, -25)

    event(rw, rec, "seen_again", finding=finding25, explanation=expl25)
    shown = one(rw, """SELECT f.action->>'change_pct' FROM recommendation_events e JOIN findings f ON f.id = e.finding_id
                       WHERE e.recommendation_id = %s AND e.type = 'seen_again'
                       ORDER BY e.created_at DESC, e.id DESC LIMIT 1""", rec)
    assert shown == "-25"

    event(rw, rec, "done", actor=user, finding=finding25)

    # замер старой версии −15% невозможен: человек выполнял −25%
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        result(rw, chain, rec, finding15)

    res = result(rw, chain, rec, finding25)
    event(rw, rec, "measured", finding=finding25, result=res)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):  # measured не может указывать на другую версию
        event(rw, rec, "measured", finding=finding15, result=res)

    measured = one(rw, """SELECT f.action->>'change_pct' FROM recommendation_results r JOIN findings f ON f.id = r.finding_id
                          WHERE r.recommendation_id = %s""", rec)
    assert measured == "-25"
