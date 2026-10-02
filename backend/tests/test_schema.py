"""Инварианты схемы БД (docs/DATA_MODEL.md §5, §8, §9): то, что должна гарантировать сама база, а не код."""

import hashlib
import itertools
from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.worker.measure import execution_date

_seq = itertools.count(1)
# Один момент события: из него и created_at, и день выполнения (как будет делать API) — без флейка около полуночи.
EVENT_AT = datetime.now(timezone.utc)
EXECUTED = execution_date(EVENT_AT)


def value(**overrides) -> dict:
    v = {
        "amount": "12400.00", "unit": "rub", "source": "yandex_direct",
        "period_from": "2026-09-22", "period_to": "2026-09-28",
        "calculation_type": "actual", "data_status": "complete", "data_sufficiency": "sufficient",
        "snapshot_id": 1, "rule_version": None, "formula": None,
    }
    return {**v, **overrides}


def key(*parts) -> bytes:
    return hashlib.sha256("|".join(map(str, parts)).encode()).digest()


def connected(conn, kind, workspace_id, login, token=b"\x01") -> int:
    """Подключение как в продукте: строка без токена → set_connection_token (шифротекст приложению недоступен)."""
    table = {"direct": "direct_connections", "metrika": "metrika_connections"}[kind]
    cid = conn.execute(f"INSERT INTO {table} (workspace_id, yandex_login, status) VALUES (%s, %s, 'disconnected') "
                       "RETURNING id", (workspace_id, login)).fetchone()[0]
    conn.execute("SELECT set_connection_token(%s, %s, %s, %s, NULL)", (kind, workspace_id, cid, token))
    return cid


def one(conn, sql, *params):
    return conn.execute(sql, params).fetchone()[0]


def new_workspace(conn, name="w", *, user=None, kind="business") -> int:
    """Workspace в своей организации; её owner — user (или новый пользователь): без owner организации не бывает."""
    with conn.transaction():
        if user is None:
            user = one(conn, "INSERT INTO users (email) VALUES (%s) RETURNING id", f"owner{next(_seq)}@example.test")
        org = one(conn, "INSERT INTO organizations (name, kind) VALUES (%s, %s) RETURNING id", name, kind)
        conn.execute("INSERT INTO organization_memberships (user_id, organization_id, org_role) VALUES (%s, %s, 'owner')",
                     (user, org))
        return one(conn, "INSERT INTO workspaces (organization_id, name) VALUES (%s, %s) RETURNING id", org, name)


@pytest.fixture
def chain(rw):
    """Полная доказательная цепочка до рекомендации. Возвращает словарь ID."""
    n = next(_seq)
    ids = {}
    ids["user"] = one(rw, "INSERT INTO users (email) VALUES (%s) RETURNING id", f"u{n}@example.test")
    ids["ws"] = new_workspace(rw, user=ids["user"])  # пользователь цепочки — owner организации workspace
    conn_id = connected(rw, "direct", ids["ws"], f"login{n}")
    ids["account"] = one(rw, "INSERT INTO direct_accounts (direct_connection_id, is_selected) VALUES (%s, true) RETURNING id", conn_id)
    ids["release"] = one(rw, "INSERT INTO releases (commit_sha, build_id) VALUES (%s, %s) RETURNING id", "a" * 40, f"b{n}")
    sync = one(rw, """INSERT INTO sync_runs (workspace_id, direct_account_id, kind, status, finished_at)
                      VALUES (%s, %s, 'scheduled', 'succeeded', now()) RETURNING id""", ids["ws"], ids["account"])
    ids["snapshot"] = one(rw, """INSERT INTO snapshots (workspace_id, sync_run_id, release_id, period_from, period_to,
                                   data_until, partial_from, sources)
                                 VALUES (%s, %s, %s, '2026-08-25', '2026-09-30', now(), '2026-09-28', '{yandex_direct}')
                                 RETURNING id""", ids["ws"], sync, ids["release"])
    rw.execute("UPDATE snapshots SET status = 'complete', sealed_at = now() WHERE id = %s", (ids["snapshot"],))
    audit = one(rw, """INSERT INTO audit_runs (workspace_id, release_id, kind, task_key, data_cutoff, settings, rules_run)
                       VALUES (%s, %s, 'scheduled', gen_random_uuid()::text, '2026-09-30', '{}', '{high_cpa_target@1}')
                       RETURNING id""", ids["ws"], ids["release"])
    ids["issue_key"] = key(ids["ws"], ids["account"], "high_cpa", "campaign", 12345, "")
    ids["issue"] = one(rw, """INSERT INTO issues (workspace_id, direct_account_id, issue_key, issue_type, object_type, object_id)
                              VALUES (%s, %s, %s, 'high_cpa', 'campaign', 12345) RETURNING id""",
                       ids["ws"], ids["account"], ids["issue_key"])
    ids["finding"] = one(rw, """INSERT INTO findings (audit_run_id, issue_id, rule_version, lost, recoverable,
                                  data_quality, evidence, action, safety_policy, candidate_level, action_level)
                                VALUES (%s, %s, 'high_cpa_target@1', %s, %s, 'medium', %s, %s, 'safety_policy@1', 'review', 'review') RETURNING id""",
                         audit, ids["issue"], Jsonb(value()),
                         Jsonb(value(calculation_type="estimated", formula="(cpa - target) * conv")),
                         Jsonb({"clicks": value(unit="count", amount=487)}),
                         Jsonb({"type": "decrease_bid", "change_pct": -15}))
    ids["explanation"] = one(rw, """INSERT INTO explanations (finding_id, source, text, release_id)
                                    VALUES (%s, 'template', 'CPA выше цели', %s) RETURNING id""",
                             ids["finding"], ids["release"])
    ids["rec"] = one(rw, "INSERT INTO recommendations (issue_id, finding_id, explanation_id) VALUES (%s, %s, %s) RETURNING id",
                     ids["issue"], ids["finding"], ids["explanation"])
    return ids


# --- Контракт Value --------------------------------------------------------------------------------

@pytest.mark.parametrize("v, ok", [
    (value(), True),
    (value(calculation_type="estimated", formula="a / b"), True),
    (value(amount=None, calculation_type="unavailable", data_sufficiency="insufficient"), True),
    (value(amount=None), False),                                             # число пропало, а тип actual
    (value(calculation_type="unavailable", data_sufficiency="insufficient"), False),  # unavailable с числом
    (value(data_sufficiency="insufficient"), False),                         # insufficient ⇔ unavailable
    (value(calculation_type="estimated"), False),                            # estimated без формулы
    (value(period_from="2026-09-29"), False),                                # период задом наперёд
    (value(unit="usd"), False),
    ({k: v for k, v in value().items() if k != "snapshot_id"}, False),       # нет обязательного поля
])
def test_value_contract(rw, v, ok):
    assert one(rw, "SELECT value_is_valid(%s)", Jsonb(v)) is ok


# --- Append-only и роли ----------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "UPDATE findings SET data_quality = 'high' WHERE id = %s",
    "DELETE FROM findings WHERE id = %s",
])
def test_app_cannot_rewrite_history(rw, chain, sql):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        rw.execute(sql, (chain["finding"],))


def test_trigger_blocks_even_table_owner(db, chain):
    # У app нет UPDATE по правам — триггер там не доходит до дела. Проверяем его на владельце, у которого права есть.
    with db("app_migrator") as owner:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            owner.execute("UPDATE findings SET data_quality = 'high' WHERE id = %s", (chain["finding"],))


def test_app_cannot_alter_schema(rw):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        rw.execute("ALTER TABLE findings DISABLE TRIGGER findings_append_only")


@pytest.mark.parametrize("sql", [
    "SELECT count(*) FROM explanations",
    "DELETE FROM recommendations WHERE id = %(rec)s",
    "DELETE FROM free_audit_claims",                    # отметки бесплатного аудита переживают удаление
    "UPDATE explanations SET text = 'x' WHERE id = %(expl)s",
    "INSERT INTO releases (commit_sha, build_id) VALUES (repeat('a', 40), 'x')",
])
def test_deleter_role_can_only_call_deletion_functions(db, chain, sql):
    """У роли удаления нет прав на таблицы: удалить можно только вызовом delete_workspace_data / purge."""
    with db("app_deleter") as dl, pytest.raises(psycopg.errors.InsufficientPrivilege):
        dl.execute(sql, {"rec": chain["rec"], "expl": chain["explanation"]})


def test_deletion_marker_cannot_be_forged_by_app(rw, chain):
    """Метку app.deleting может выставить кто угодно, но без права DELETE она ничего не даёт."""
    with rw.transaction():
        rw.execute("SELECT set_config('app.deleting', 'on', true)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            rw.execute("DELETE FROM explanations WHERE id = %s", (chain["explanation"],))


# --- Идентичность проблемы и рекомендации ----------------------------------------------------------

def test_one_open_issue_per_key(rw, chain):
    insert = """INSERT INTO issues (workspace_id, direct_account_id, issue_key, issue_type, object_type, object_id)
                VALUES (%s, %s, %s, 'high_cpa', 'campaign', 12345)"""
    with pytest.raises(psycopg.errors.UniqueViolation):
        rw.execute(insert, (chain["ws"], chain["account"], chain["issue_key"]))
    rw.execute("UPDATE issues SET closed_at = now(), close_reason = 'resolved' WHERE id = %s", (chain["issue"],))
    rw.execute(insert, (chain["ws"], chain["account"], chain["issue_key"]))  # новый жизненный цикл — можно


def test_one_recommendation_per_issue(rw, chain):
    with pytest.raises(psycopg.errors.UniqueViolation):
        rw.execute("INSERT INTO recommendations (issue_id, finding_id, explanation_id) VALUES (%s, %s, %s)",
                   (chain["issue"], chain["finding"], chain["explanation"]))


def test_explanation_must_belong_to_finding(rw, chain):
    other = chain_factory_second_finding(rw, chain)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        rw.execute("INSERT INTO recommendations (issue_id, finding_id, explanation_id) VALUES (%s, %s, %s)",
                   (other["issue"], other["finding"], chain["explanation"]))


def chain_factory_second_finding(rw, chain):
    audit = one(rw, "SELECT audit_run_id FROM findings WHERE id = %s", chain["finding"])
    issue = one(rw, """INSERT INTO issues (workspace_id, direct_account_id, issue_key, issue_type, object_type, object_id)
                       VALUES (%s, %s, %s, 'zero_conv_campaign', 'campaign', 777) RETURNING id""",
                chain["ws"], chain["account"], key(chain["ws"], "zero_conv", 777))
    finding = one(rw, """INSERT INTO findings (audit_run_id, issue_id, rule_version, lost, recoverable, data_quality, evidence, action, safety_policy, candidate_level, action_level)
                         VALUES (%s, %s, 'zero_conv_campaign@1', %s, %s, 'high', '{}', '{"type": "pause"}', 'safety_policy@1', 'review', 'review') RETURNING id""",
                  audit, issue, Jsonb(value()), Jsonb(value()))
    return {"issue": issue, "finding": finding}


@pytest.mark.parametrize("type_, actor, finding, explanation, payload, day, ok", [
    ("done", True, True, False, {}, 0, True),
    ("done", False, True, False, {}, 0, False),           # действие человека без автора
    ("done", True, False, False, {}, 0, False),           # не указано, какую версию действия выполнили
    ("done", True, True, False, {}, None, False),         # без дня выполнения — окна замера не от чего считать
    ("done", True, True, False, {}, -3, False),           # задним числом: вне ±1 дня от UTC-даты события
    ("seen_again", False, True, False, {}, None, False),  # пересчёт без объяснения к нему
    ("seen_again", False, True, True, {}, None, True),
    ("resolved", False, False, False, {}, None, True),
    ("resolved", True, False, False, {}, None, False),    # системное событие от имени пользователя
    ("resolved", False, True, False, {}, None, False),    # finding только у seen_again / done / measured
    ("resolved", False, False, False, {}, 0, False),      # день выполнения — только у done
    ("postponed", True, False, False, {}, None, False),   # отложить без даты
    ("postponed", True, False, False, {"until": "2026-10-05"}, None, True),
])
def test_recommendation_event_shape(rw, chain, type_, actor, finding, explanation, payload, day, ok):
    sql = """INSERT INTO recommendation_events (recommendation_id, type, actor_user_id, finding_id, explanation_id,
                                                payload, execution_date, created_at)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
    params = (chain["rec"], type_, chain["user"] if actor else None,
              chain["finding"] if finding else None, chain["explanation"] if explanation else None, Jsonb(payload),
              None if day is None else EXECUTED + timedelta(days=day), EVENT_AT)
    if ok:
        rw.execute(sql, params)
    else:
        with pytest.raises(psycopg.errors.CheckViolation):
            rw.execute(sql, params)


@pytest.mark.parametrize("day, ok", [
    (date(2026, 10, 1), True),   # верно: 21:30 UTC 30.09 — это 1.10 в Москве
    (date(2026, 9, 30), True),   # НЕВЕРНО, но БД пропускает: она проверяет диапазон, не точность дня
    (date(2026, 9, 28), False),  # вне ±1 дня от UTC-даты — отклоняется
])
def test_execution_date_db_check_is_sanity_only(rw, chain, day, ok):
    """Точность дня выполнения гарантирует приложение (execution_date), БД — только вторая линия: ±1 день."""
    at = datetime(2026, 9, 30, 21, 30, tzinfo=timezone.utc)
    assert execution_date(at) == date(2026, 10, 1)
    sql = """INSERT INTO recommendation_events (recommendation_id, type, actor_user_id, finding_id, execution_date,
                                                created_at)
             VALUES (%s, 'done', %s, %s, %s, %s)"""
    params = (chain["rec"], chain["user"], chain["finding"], day, at)
    if ok:
        rw.execute(sql, params)
    else:
        with pytest.raises(psycopg.errors.CheckViolation):
            rw.execute(sql, params)


def test_saved_only_with_effect(rw, chain):
    rw.execute("""INSERT INTO recommendation_events (recommendation_id, type, actor_user_id, finding_id, execution_date,
                                                     created_at)
                  VALUES (%s, 'done', %s, %s, %s, %s)""",
               (chain["rec"], chain["user"], chain["finding"], EXECUTED, EVENT_AT))
    sql = """INSERT INTO recommendation_results (recommendation_id, finding_id, snapshot_id, release_id, before, after, saved, verdict)
             VALUES (%s, %s, %s, %s, '{}', '{}', %s, %s)"""
    base = (chain["rec"], chain["finding"], chain["snapshot"], chain["release"])
    with pytest.raises(psycopg.errors.CheckViolation):
        rw.execute(sql, (*base, None, "effect"))
    with pytest.raises(psycopg.errors.CheckViolation):
        rw.execute(sql, (*base, Jsonb(value(calculation_type="estimated", formula="f")), "no_effect"))
    rw.execute(sql, (*base, Jsonb(value(calculation_type="estimated", formula="before - after")), "effect"))


# --- Подписки и подключения ------------------------------------------------------------------------

def test_auto_renew_requires_explicit_consent(rw, chain):
    sql = """INSERT INTO subscriptions (workspace_id, plan, status, price, current_period_start, current_period_end,
               auto_renew, renew_consent_at, payment_method_ref)
             VALUES (%s, 'start', 'active', 4990, now(), now() + interval '1 month', true, %s, %s)"""
    with pytest.raises(psycopg.errors.CheckViolation):
        rw.execute(sql, (chain["ws"], None, "pm_1"))
    rw.execute(sql, (chain["ws"], "2026-09-29", "pm_1"))
    with pytest.raises(psycopg.errors.UniqueViolation):  # вторая активная подписка
        rw.execute(sql, (chain["ws"], "2026-09-29", "pm_2"))


def test_disconnected_connection_has_no_token(rw, chain):
    with pytest.raises(psycopg.errors.CheckViolation):
        rw.execute("""UPDATE direct_connections SET status = 'disconnected'
                      WHERE id = (SELECT direct_connection_id FROM direct_accounts WHERE id = %s)""", (chain["account"],))


# --- Зернистость stat_rows -------------------------------------------------------------------------

STAT = """INSERT INTO stat_rows (snapshot_id, source, level, object_id, campaign_id, date, clicks, cost)
          VALUES (%s, %s, %s, %s, %s, %s, 1, 10)"""


def new_snapshot(rw, chain) -> int:
    """Снимок новой синхронизации. Вызывать внутри транзакции, в которой пишутся его строки."""
    sync = one(rw, """INSERT INTO sync_runs (workspace_id, direct_account_id, kind, status, finished_at)
                      VALUES (%s, %s, 'resync', 'succeeded', now()) RETURNING id""", chain["ws"], chain["account"])
    return one(rw, """INSERT INTO snapshots (workspace_id, sync_run_id, release_id, period_from, period_to,
                        data_until, partial_from, sources)
                      VALUES (%s, %s, %s, '2026-08-25', '2026-09-30', now(), '2026-09-28', '{yandex_direct}')
                      RETURNING id""", chain["ws"], sync, chain["release"])


def test_same_query_in_two_campaigns_is_two_rows(rw, chain):
    with rw.transaction():
        s = new_snapshot(rw, chain)
        rw.execute(STAT, (s, "yandex_direct", "query", 501, 1, "2026-09-01"))
        rw.execute(STAT, (s, "yandex_direct", "query", 501, 2, "2026-09-01"))  # другая кампания — другое наблюдение
        rw.execute(STAT, (s, "yandex_direct", "query", 501, 1, "2026-09-02"))  # другой день — тоже
        with pytest.raises(psycopg.errors.UniqueViolation):                    # то же наблюдение дважды — нет
            with rw.transaction():
                rw.execute(STAT, (s, "yandex_direct", "query", 501, 1, "2026-09-01"))


@pytest.mark.parametrize("level, object_id, campaign_id", [
    ("query", 501, None),        # уровень Директа без кампании
    ("campaign", 7, 8),          # на уровне кампании объект обязан быть самой кампанией
    ("site_goal", 9, 1),         # цель сайта Метрики не принадлежит кампании
])
def test_stat_row_grain_checks(rw, chain, level, object_id, campaign_id):
    with pytest.raises(psycopg.errors.CheckViolation), rw.transaction():
        s = new_snapshot(rw, chain)
        rw.execute(STAT, (s, "yandex_direct", level, object_id, campaign_id, "2026-09-01"))


def test_site_goal_without_campaign_is_unique_too(rw, chain):
    with rw.transaction():
        s = new_snapshot(rw, chain)
        rw.execute(STAT, (s, "yandex_metrika", "site_goal", 9, None, "2026-09-01"))
        with pytest.raises(psycopg.errors.UniqueViolation), rw.transaction():
            rw.execute(STAT, (s, "yandex_metrika", "site_goal", 9, None, "2026-09-01"))


# --- Жизненный цикл снимка: building → complete | failed, только вперёд ---------------------------

def test_rows_can_be_added_only_while_building(rw, chain):
    s = new_snapshot(rw, chain)
    rw.execute(STAT, (s, "yandex_direct", "campaign", 1, 1, "2026-09-01"))  # building: можно, даже в другой транзакции
    rw.execute("UPDATE snapshots SET status = 'complete', sealed_at = now() WHERE id = %s", (s,))
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):     # complete: запечатан
        rw.execute(STAT, (s, "yandex_direct", "campaign", 1, 1, "2026-09-02"))


def test_rows_cannot_be_added_to_failed_snapshot(rw, chain):
    s = new_snapshot(rw, chain)
    rw.execute("UPDATE snapshots SET status = 'failed' WHERE id = %s", (s,))
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute(STAT, (s, "yandex_direct", "campaign", 1, 1, "2026-09-01"))


@pytest.mark.parametrize("start, sql", [
    ("complete", "UPDATE snapshots SET status = 'building', sealed_at = NULL WHERE id = %s"),
    ("complete", "UPDATE snapshots SET status = 'failed', sealed_at = NULL WHERE id = %s"),
    ("complete", "UPDATE snapshots SET sealed_at = now() + interval '1 day' WHERE id = %s"),  # тот же статус
    ("failed", "UPDATE snapshots SET status = 'complete', sealed_at = now() WHERE id = %s"),
    ("failed", "UPDATE snapshots SET status = 'building' WHERE id = %s"),
    ("building", "UPDATE snapshots SET period_to = '2026-10-01', status = 'complete', sealed_at = now() WHERE id = %s"),
])
def test_snapshot_state_moves_only_forward(rw, chain, start, sql):
    s = new_snapshot(rw, chain)
    if start != "building":
        rw.execute("UPDATE snapshots SET status = %s, sealed_at = %s WHERE id = %s",
                   (start, "2026-09-30" if start == "complete" else None, s))
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute(sql, (s,))


def test_snapshot_cannot_be_created_already_complete(rw, chain):
    sync = one(rw, """INSERT INTO sync_runs (workspace_id, direct_account_id, kind) VALUES (%s, %s, 'resync')
                      RETURNING id""", chain["ws"], chain["account"])
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute("""INSERT INTO snapshots (workspace_id, sync_run_id, release_id, period_from, period_to, data_until,
                        partial_from, sources, status, sealed_at)
                      VALUES (%s, %s, %s, '2026-08-25', '2026-09-30', now(), '2026-09-28', '{yandex_direct}',
                              'complete', now())""", (chain["ws"], sync, chain["release"]))


def test_snapshot_cannot_be_deleted_by_app(rw, chain):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        rw.execute("DELETE FROM snapshots WHERE id = %s", (new_snapshot(rw, chain),))


def audit_run(rw, chain, cutoff="2026-09-30") -> int:
    return one(rw, """INSERT INTO audit_runs (workspace_id, release_id, kind, task_key, data_cutoff, settings, rules_run)
                      VALUES (%s, %s, 'scheduled', gen_random_uuid()::text, %s, '{}', '{}') RETURNING id""",
               chain["ws"], chain["release"], cutoff)


LINK = "INSERT INTO audit_run_snapshots (audit_run_id, direct_account_id, snapshot_id) VALUES (%s, %s, %s)"


def test_audit_requires_complete_snapshot(rw, chain):
    """Воркер не может принять снимок в сборке за готовый: база не даст построить на нём аудит."""
    s = new_snapshot(rw, chain)
    audit = audit_run(rw, chain)
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute(LINK, (audit, chain["account"], s))
    rw.execute("UPDATE snapshots SET status = 'complete', sealed_at = now() WHERE id = %s", (s,))
    rw.execute(LINK, (audit, chain["account"], s))


@pytest.mark.parametrize("cutoff, other_account", [
    ("2026-09-29", False),   # снимок на 30-е в аудите на 29-е — разные дни не смешиваются
    ("2026-09-30", True),    # снимок чужого аккаунта
])
def test_audit_snapshot_must_fit_cutoff_and_account(rw, chain, cutoff, other_account):
    audit = audit_run(rw, chain, cutoff)
    account = chain["account"]
    if other_account:
        conn = connected(rw, "direct", chain["ws"], f"other{audit}")
        account = one(rw, "INSERT INTO direct_accounts (direct_connection_id) VALUES (%s) RETURNING id", conn)
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute(LINK, (audit, account, chain["snapshot"]))


def test_one_snapshot_per_account_in_audit(rw, chain):
    audit = audit_run(rw, chain)
    rw.execute(LINK, (audit, chain["account"], chain["snapshot"]))
    with pytest.raises(psycopg.errors.UniqueViolation):
        rw.execute(LINK, (audit, chain["account"], chain["snapshot"]))


@pytest.mark.parametrize("column", ["lost", "recoverable"])
def test_negative_loss_cannot_enter_immutable_evidence(rw, chain, column):
    """Ошибка правила не должна навсегда записать «потеряно −5 000 ₽»: доказательства потом не исправить."""
    audit = one(rw, "SELECT audit_run_id FROM findings WHERE id = %s", chain["finding"])
    issue = one(rw, """INSERT INTO issues (workspace_id, direct_account_id, issue_key, issue_type, object_type, object_id)
                       VALUES (%s, %s, %s, 'zero_conv_campaign', 'campaign', 778) RETURNING id""",
                chain["ws"], chain["account"], key(chain["ws"], "negative", 778))
    amounts = {"lost": value(), "recoverable": value(), column: value(amount="-5000.00")}
    with pytest.raises(psycopg.errors.CheckViolation):
        rw.execute("""INSERT INTO findings (audit_run_id, issue_id, rule_version, lost, recoverable, data_quality,
                      evidence, action, safety_policy, candidate_level, action_level)
                      VALUES (%s, %s, 'zero_conv_campaign@1', %s, %s, 'high', '{}', '{"type": "pause"}',
                              'safety_policy@1', 'review', 'review')""",
                   (audit, issue, Jsonb(amounts["lost"]), Jsonb(amounts["recoverable"])))
