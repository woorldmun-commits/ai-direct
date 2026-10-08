"""Политика безопасных рекомендаций safety_policy@1: правило предлагает, политика только понижает.
Мало данных — никаких изменений настроек; стратегия неизвестна — не выше review; БД не даёт повысить уровень."""

import dataclasses

import psycopg
import pytest

from app.audit.policy import CANDIDATE_LEVEL, LEVELS, decide
from app.audit.templates import explain
from test_rule_high_cpa import NO_TARGET, TARGET, audit, only, snap
from test_direct_sync import root  # noqa: F401 — фикстура
from test_metrika_sync import metrika  # noqa: F401 — фикстура
from test_schema import EVENT_AT, EXECUTED, chain, one, value  # noqa: F401 — фикстура
from test_worker_audit import audit as worker_audit, fresh, sync  # noqa: F401 — fresh: autouse-фикстура
from test_worker_sync import ws  # noqa: F401 — фикстура


def finding(conv=8, settings=TARGET):
    return only(audit(snap(eval_cost=5250 * conv, eval_conv=conv), settings))


@pytest.mark.parametrize("conv, level, reasons", [
    (1, "inspect_only", ("data_sufficiency_low", "strategy_unknown")),    # 1–2 конверсии: только проверить
    (2, "inspect_only", ("data_sufficiency_low", "strategy_unknown")),
    (8, "review", ("data_sufficiency_medium", "strategy_unknown")),
    (12, "review", ("strategy_unknown",)),                                 # данных хватает, но стратегия неизвестна
])
def test_bid_change_is_downgraded_by_data_and_unknown_strategy(conv, level, reasons):
    f = finding(conv)
    assert f.action["type"] == "decrease_bid"                             # правило предлагает кандидата всегда
    d = decide(f)
    assert (d.candidate_level, d.level, d.reasons, d.version) == ("change", level, reasons, "safety_policy@1")


def test_investigation_stays_inspect_only():
    d = decide(finding(settings=NO_TARGET))
    assert (d.candidate_level, d.level, d.reasons) == ("inspect_only", "inspect_only", ())


def test_candidate_levels_of_v1_actions_are_explicit():
    """Каждое действие трёх правил v1.0 — явно в политике: «проверить» — inspect_only, исключение площадок —
    review (change не бывает). Раньше два последних шли веткой «неизвестное действие» — тоже inspect_only."""
    assert CANDIDATE_LEVEL == {"decrease_bid": "change", "investigate_cpa_growth": "inspect_only",
                               "investigate_zero_conversions": "inspect_only", "exclude_placements": "review"}


@pytest.mark.parametrize("quality, level, reasons", [
    ("low", "inspect_only", ("data_sufficiency_low",)),
    ("medium", "review", ()),
    ("high", "review", ()),            # данных много — но кандидат review, политика не повышает до change
])
def test_exclude_placements_is_never_above_review(quality, level, reasons):
    from test_rule_zero_conv_placements import CID, DONE, evaluate, pday
    (f,) = evaluate([pday(CID, "a.ru", DONE, "15000.00", 500, "0")])
    d = decide(dataclasses.replace(f, current_data_quality=quality))
    assert (d.candidate_level, d.level, d.reasons) == ("review", level, reasons)


def test_investigate_zero_conversions_stays_inspect_only_at_any_data():
    from test_rule_zero_conv_campaign import TARGET as ZC_TARGET, audit as zc_audit, only as zc_only, snap as zc_snap
    f = zc_only(zc_audit(zc_snap(eval_cost=90000, eval_clicks=900), ZC_TARGET))
    assert f.current_data_quality == "high"
    assert decide(f).level == "inspect_only"


def test_unknown_action_offers_no_change():
    """Новое правило с неизвестным политике действием не может обойти её: только «проверить»."""
    f = dataclasses.replace(finding(12), action={"type": "raise_budget", "change_pct": 50})
    assert decide(f).level == "inspect_only"


@pytest.mark.parametrize("conv", [1, 2, 3, 8, 10, 50])
def test_policy_never_raises_level(conv):
    d = decide(finding(conv))
    assert LEVELS.index(d.level) <= LEVELS.index(d.candidate_level)
    assert (d.level == d.candidate_level) == (d.reasons == ())


def test_low_data_explanation_suggests_no_bid_change():
    f = finding(1)
    text = explain(f, decide(f))
    assert "снизить ставку" not in text and "продолжаем наблюдать" in text


def test_review_explanation_asks_to_check_strategy():
    f = finding(8)
    text = explain(f, decide(f))
    assert "рычаги кампании" in text and "снизить ставку" not in text  # стратегия неизвестна: ставку не советуем
    assert "проверьте перед изменением" in explain(f, decide(f), "manual")  # ручная — совет остаётся


# --- Инварианты в БД ---------------------------------------------------------------------------------

def insert(rw, chain, candidate, level, reasons):
    audit_run = one(rw, """INSERT INTO audit_runs (workspace_id, release_id, kind, task_key, data_cutoff, settings, rules_run)
                           VALUES (%s, %s, 'scheduled', gen_random_uuid()::text, '2026-09-30', '{}', '{}')
                           RETURNING id""", chain["ws"], chain["release"])
    rw.execute("""INSERT INTO findings (audit_run_id, issue_id, rule_version, lost, recoverable, data_quality, evidence,
                                        action, safety_policy, candidate_level, action_level, policy_reasons)
                  VALUES (%s, %s, 'high_cpa_target@1', %s, %s, 'low', '{}', '{"type": "decrease_bid"}',
                          'safety_policy@1', %s, %s, %s)""",
               (audit_run, chain["issue"], psycopg.types.json.Jsonb(value()), psycopg.types.json.Jsonb(value()),
                candidate, level, reasons))


@pytest.mark.parametrize("candidate, level, reasons", [
    ("inspect_only", "change", []),                      # политика повысила уровень
    ("review", "change", ["x"]),
    ("change", "inspect_only", []),                      # понижено без причины
    ("change", "change", ["data_sufficiency_low"]),      # причина есть, а понижения нет
])
def test_db_rejects_raised_level_and_unexplained_downgrade(rw, chain, candidate, level, reasons):
    with pytest.raises(psycopg.errors.CheckViolation):
        insert(rw, chain, candidate, level, reasons)


def test_db_accepts_valid_downgrade(rw, chain):
    insert(rw, chain, "change", "inspect_only", ["data_sufficiency_low", "strategy_unknown"])


def test_audit_stores_policy_decision_and_explains_it(rw, ws):
    """Сквозной путь: аудит → правило → политика → finding с обеими версиями и текст по разрешённому уровню."""
    rw.execute("INSERT INTO workspace_settings (workspace_id, target_cpa) VALUES (%s, 3000)", (ws["ws"],))
    sync(rw, ws)
    worker_audit(rw, ws, "policy")
    row = rw.execute("""SELECT f.rule_version, f.safety_policy, f.action->>'type', f.candidate_level, f.action_level,
                               f.policy_reasons, x.text
                        FROM findings f JOIN issues i ON i.id = f.issue_id JOIN explanations x ON x.finding_id = f.id
                        WHERE i.workspace_id = %s ORDER BY f.id DESC LIMIT 1""", (ws["ws"],)).fetchone()  # не из chain
    assert row[:6] == ("high_cpa_target@2", "safety_policy@2", "decrease_bid", "change", "review",
                       ["data_sufficiency_medium", "conversions_partial", "strategy_unknown"])  # 8 конверсий — medium;
    # конверсии окна — за дни досчёта (safety_policy@2)
    assert "рычаги кампании" in row[6] and "снизить ставку" not in row[6]


# --- «Проверил» ≠ «Я сделал это»: замер «Сэкономлено» — только после изменения ------------------------

def recommendation_after_audit(rw, ws, target=None):
    if target:
        rw.execute("INSERT INTO workspace_settings (workspace_id, target_cpa) VALUES (%s, %s)", (ws["ws"], target))
    sync(rw, ws)
    worker_audit(rw, ws, "outcome")
    return rw.execute("""SELECT r.id, r.finding_id, f.action_level FROM recommendations r
                         JOIN issues i ON i.id = r.issue_id JOIN findings f ON f.id = r.finding_id
                         WHERE i.workspace_id = %s ORDER BY r.id DESC LIMIT 1""", (ws["ws"],)).fetchone()


def human(rw, ws, rec, finding, type_):
    rw.execute("""INSERT INTO recommendation_events (recommendation_id, type, actor_user_id, finding_id, execution_date,
                                                     created_at) VALUES (%s, %s, %s, %s, %s, %s)""",
               (rec, type_, ws["user"], finding, EXECUTED if type_ == "done" else None, EVENT_AT))


def measurements(rw, rec):
    return one(rw, "SELECT count(*) FROM measurements WHERE recommendation_id = %s", rec)


def test_inspect_only_is_checked_and_never_measured(rw, ws):
    rec, finding, level = recommendation_after_audit(rw, ws)                 # без цели: «проверить причину»
    assert level == "inspect_only"
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="done is not allowed"):
        human(rw, ws, rec, finding, "done")                                  # «сделал» — нечего было делать
    human(rw, ws, rec, finding, "checked")
    assert measurements(rw, rec) == 0                                        # «Сэкономлено» после проверки нет


def test_suggested_change_is_done_and_measured(rw, ws):
    rec, finding, level = recommendation_after_audit(rw, ws, target=3000)
    assert level == "review"
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="checked is not allowed"):
        human(rw, ws, rec, finding, "checked")                               # изменение предлагали — не «проверка»
    human(rw, ws, rec, finding, "done")
    assert measurements(rw, rec) == 1


def test_checked_needs_author_and_version(rw, ws):
    rec, finding, _ = recommendation_after_audit(rw, ws)
    with pytest.raises(psycopg.errors.CheckViolation):
        rw.execute("INSERT INTO recommendation_events (recommendation_id, type, finding_id) VALUES (%s, 'checked', %s)",
                   (rec, finding))                                           # без автора
    with pytest.raises(psycopg.errors.CheckViolation):
        rw.execute("""INSERT INTO recommendation_events (recommendation_id, type, actor_user_id)
                      VALUES (%s, 'checked', %s)""", (rec, ws["user"]))      # без версии вывода
