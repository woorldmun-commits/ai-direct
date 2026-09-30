"""Сквозной жизненный цикл одного workspace на уровне БД:
signup → подключения → бесплатный аудит → 37-дневная синхронизация → аудит → рекомендация → пересчёт →
выполнение → замер → подписка (продление, неуспех, истечение) → деактивация → удаление.

Цель — найти противоречия между таблицами, ограничениями и ролями, которые не видны в тестах по одной таблице.
Правила guard проверяются отдельно, когда появится код воркера."""

import datetime as dt
import hashlib

import psycopg
import pytest
from psycopg.types.json import Jsonb

from test_schema import EVENT_AT, EXECUTED, connected, value

D0 = dt.date(2026, 8, 24)  # первый день 37-дневного окна
DAYS = 37


def one(conn, sql, *params):
    return conn.execute(sql, params).fetchone()[0]


def sync(rw, ws, account, release, cpa_cost: int):
    """Успешная синхронизация: sync_run → снимок на 37 дней → агрегаты кампании 12345."""
    run = one(rw, "INSERT INTO sync_runs (workspace_id, direct_account_id, kind) VALUES (%s, %s, 'scheduled') RETURNING id",
              ws, account)
    rw.execute("UPDATE sync_runs SET status = 'running', started_at = now() WHERE id = %s", (run,))
    with rw.transaction():  # снимок и succeeded — в одной транзакции (инвариант 1)
        rw.execute("UPDATE sync_runs SET status = 'succeeded', finished_at = now() WHERE id = %s", (run,))
        snap = one(rw, """INSERT INTO snapshots (workspace_id, sync_run_id, release_id, period_from, period_to,
                            data_until, partial_from, sources, conversion_definition)
                          VALUES (%s, %s, %s, %s, %s, now(), %s, '{yandex_direct,yandex_metrika}',
                                  '{"provider": "yandex_metrika", "counter_id": 555, "goal_ids": [1, 2],
                                    "attribution": "cross_device_last_significant"}') RETURNING id""",
                   ws, run, release, D0, D0 + dt.timedelta(DAYS - 1), D0 + dt.timedelta(DAYS - 3))
        with rw.cursor() as cur:
            cur.executemany(
                """INSERT INTO stat_rows (snapshot_id, source, level, object_id, campaign_id, date,
                     impressions, clicks, cost, conversions)
                   VALUES (%s, 'yandex_direct', 'campaign', 12345, 12345, %s, 1000, 70, %s, 1)""",
                [(snap, D0 + dt.timedelta(i), cpa_cost) for i in range(DAYS)])
        rw.execute("UPDATE snapshots SET status = 'complete', sealed_at = now() WHERE id = %s", (snap,))
    return snap


def audit(rw, ws, account, snap, release, issue_key, change_pct):
    """Аудит находит high_cpa по кампании 12345. Возвращает (audit_run, issue, finding, explanation)."""
    run = one(rw, """INSERT INTO audit_runs (workspace_id, release_id, kind, task_key, data_cutoff, settings, rules_run)
                     VALUES (%s, %s, 'scheduled', gen_random_uuid()::text, %s, %s, '{high_cpa_target@1}')
                     RETURNING id""",
              ws, release, D0 + dt.timedelta(DAYS - 1), Jsonb({"target_cpa": "3000.00", "notify_pct_threshold": 10}))
    rw.execute("INSERT INTO audit_run_snapshots (audit_run_id, direct_account_id, snapshot_id) VALUES (%s, %s, %s)",
               (run, account, snap))
    issue = rw.execute("SELECT id FROM issues WHERE issue_key = %s AND closed_at IS NULL", (issue_key,)).fetchone()
    if issue is None:
        issue_id = one(rw, """INSERT INTO issues (workspace_id, direct_account_id, issue_key, issue_type, object_type, object_id)
                              VALUES (%s, %s, %s, 'high_cpa', 'campaign', 12345) RETURNING id""", ws, account, issue_key)
    else:
        issue_id = issue[0]
    finding = one(rw, """INSERT INTO findings (audit_run_id, issue_id, rule_version, lost, recoverable, data_quality,
                           evidence, action)
                         VALUES (%s, %s, 'high_cpa_target@1', %s, %s, 'medium', %s, %s) RETURNING id""",
                  run, issue_id, Jsonb(value(snapshot_id=snap)),
                  Jsonb(value(snapshot_id=snap, calculation_type="estimated", formula="(cpa - target) * conv")),
                  Jsonb({"target_cpa": value(snapshot_id=snap, source="user_input", amount="3000.00")}),
                  Jsonb({"type": "decrease_bid", "change_pct": change_pct}))
    expl = one(rw, "INSERT INTO explanations (finding_id, source, text, release_id) VALUES (%s, 'template', %s, %s) RETURNING id",
               finding, f"Снизить ставку на {-change_pct}%", release)
    return run, issue_id, finding, expl


def current_status(rw, rec):
    return one(rw, """SELECT type FROM recommendation_events WHERE recommendation_id = %s
                      AND type NOT IN ('seen_again', 'measurement_skipped')
                      ORDER BY created_at DESC, id DESC LIMIT 1""", rec)


def test_workspace_lifecycle(db):
    rw = db("app_rw")

    # --- signup ---
    user = one(rw, "INSERT INTO users (email) VALUES ('owner@example.test') RETURNING id")
    rw.execute("INSERT INTO yandex_identities (user_id, yandex_uid, login) VALUES (%s, 'uid-lc', 'owner')", (user,))
    ws = one(rw, "INSERT INTO workspaces (name) VALUES ('ООО Ромашка') RETURNING id")
    rw.execute("INSERT INTO memberships (user_id, workspace_id) VALUES (%s, %s)", (user, ws))
    rw.execute("INSERT INTO workspace_settings (workspace_id, target_cpa) VALUES (%s, 3000)", (ws,))
    rw.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, now() + interval '30 days')",
               (hashlib.sha256(b"cookie").digest(), user))

    # --- подключения: Директ есть, Метрика сначала без прав (частичная работа) ---
    dconn = connected(rw, "direct", ws, "owner")
    account = one(rw, "INSERT INTO direct_accounts (direct_connection_id, is_selected) VALUES (%s, true) RETURNING id", dconn)
    mconn = one(rw, """INSERT INTO metrika_connections (workspace_id, yandex_login, status)
                       VALUES (%s, 'owner', 'permission_missing') RETURNING id""", ws)
    rw.execute("SELECT set_connection_token('metrika', %s, %s, '\\x02', NULL)", (ws, mconn))
    rw.execute("INSERT INTO metrika_counters (metrika_connection_id, counter_id, is_selected, goal_ids) VALUES (%s, 555, true, '{1,2}')",
               (mconn,))

    # --- бесплатный аудит: один на рекламный аккаунт ---
    claim = hashlib.sha256(b"secret|owner").digest()
    rw.execute("INSERT INTO free_audit_claims (direct_account_hash) VALUES (%s)", (claim,))
    with pytest.raises(psycopg.errors.UniqueViolation):
        rw.execute("INSERT INTO free_audit_claims (direct_account_hash) VALUES (%s)", (claim,))

    release = one(rw, "INSERT INTO releases (commit_sha, build_id) VALUES (%s, 'lc-1') RETURNING id", "c" * 40)
    issue_key = hashlib.sha256(f"{ws}|{account}|high_cpa|campaign|12345|".encode()).digest()

    # --- синхронизация 37 дней + аудит #1: -15% ---
    snap1 = sync(rw, ws, account, release, cpa_cost=5000)
    assert one(rw, "SELECT count(*) FROM stat_rows WHERE snapshot_id = %s", snap1) == DAYS
    _, issue, finding1, expl1 = audit(rw, ws, account, snap1, release, issue_key, change_pct=-15)
    rec = one(rw, "INSERT INTO recommendations (issue_id, finding_id, explanation_id) VALUES (%s, %s, %s) RETURNING id",
              issue, finding1, expl1)
    audit1 = one(rw, "SELECT audit_run_id FROM findings WHERE id = %s", finding1)
    digest = one(rw, """INSERT INTO digests (workspace_id, kind, snapshot_id, audit_run_id, payload)
                        VALUES (%s, 'daily', %s, %s, %s) RETURNING id""", ws, snap1, audit1, Jsonb({"recommendations": [rec]}))
    rw.execute("""INSERT INTO notifications (workspace_id, kind, channel, dedup_key, digest_id)
                  VALUES (%s, 'digest', 'telegram', %s, %s)""", (ws, f"digest:{ws}:2026-09-29", digest))
    query = one(rw, """INSERT INTO search_query_texts (workspace_id, text_hash, text_sanitized)
                       VALUES (%s, %s, 'купить квартиру ***') RETURNING id""", ws, hashlib.sha256(b"q").digest())
    rw.execute("INSERT INTO search_query_sightings (query_id, seen_on) VALUES (%s, %s)", (query, D0))
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):  # снимок complete — запечатан
        rw.execute("""INSERT INTO stat_rows (snapshot_id, source, level, object_id, campaign_id, date, clicks, cost, conversions)
                      VALUES (%s, 'yandex_direct', 'query', %s, 12345, %s, 12, 900, 0)""", (snap1, query, D0))

    # --- аудит #2: та же проблема, CPA вырос → пересчёт -25%, без второй рекомендации ---
    snap2 = sync(rw, ws, account, release, cpa_cost=7000)
    _, issue2, finding2, expl2 = audit(rw, ws, account, snap2, release, issue_key, change_pct=-25)
    assert issue2 == issue
    with pytest.raises(psycopg.errors.UniqueViolation):
        rw.execute("INSERT INTO recommendations (issue_id, finding_id, explanation_id) VALUES (%s, %s, %s)",
                   (issue, finding2, expl2))
    rw.execute("""INSERT INTO recommendation_events (recommendation_id, type, finding_id, explanation_id)
                  VALUES (%s, 'seen_again', %s, %s)""", (rec, finding2, expl2))
    latest_action = one(rw, """SELECT f.action->>'change_pct' FROM recommendation_events e
                               JOIN findings f ON f.id = e.finding_id
                               WHERE e.recommendation_id = %s AND e.type = 'seen_again'
                               ORDER BY e.created_at DESC, e.id DESC LIMIT 1""", rec)
    assert latest_action == "-25"

    # --- человек выполнил именно -25% ---
    rw.execute("""INSERT INTO recommendation_events (recommendation_id, type, actor_user_id, finding_id, execution_date,
                                                     created_at)
                  VALUES (%s, 'done', %s, %s, %s, %s)""", (rec, user, finding2, EXECUTED, EVENT_AT))
    assert current_status(rw, rec) == "done"

    # --- замер через 7 дней: эффект, «Сэкономлено», проблема закрыта ---
    snap3 = sync(rw, ws, account, release, cpa_cost=3200)
    result = one(rw, """INSERT INTO recommendation_results (recommendation_id, finding_id, snapshot_id, release_id, before, after, saved, verdict)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'effect') RETURNING id""",
                 rec, finding2, snap3, release,
                 Jsonb({"cost_7d": value(snapshot_id=snap3, amount="49000.00")}),
                 Jsonb({"cost_7d": value(snapshot_id=snap3, amount="22400.00")}),
                 Jsonb(value(snapshot_id=snap3, amount="26600.00", calculation_type="estimated",
                             formula="cost_before_7d - cost_after_7d")))
    rw.execute("INSERT INTO recommendation_events (recommendation_id, type, finding_id, result_id) VALUES (%s, 'measured', %s, %s)",
               (rec, finding2, result))
    rw.execute("UPDATE issues SET closed_at = now(), close_reason = 'measured' WHERE id = %s", (issue,))
    # проблема вернулась → новый жизненный цикл разрешён
    _, issue3, _, _ = audit(rw, ws, account, snap3, release, issue_key, change_pct=-5)
    assert issue3 != issue

    # --- подписка: оплата, продление, неуспешное продление, истечение, новая подписка ---
    sub = one(rw, """INSERT INTO subscriptions (workspace_id, plan, status, price, current_period_start, current_period_end,
                       auto_renew, renew_consent_at, payment_method_ref)
                     VALUES (%s, 'start', 'active', 4990, now(), now() + interval '1 month', true, now(), 'pm_1') RETURNING id""", ws)
    rw.execute("INSERT INTO subscription_events (subscription_id, type) VALUES (%s, 'paid')", (sub,))
    rw.execute("""INSERT INTO payments (subscription_id, provider, provider_payment_id, amount, status)
                  VALUES (%s, 'yookassa', 'pay-lc-1', 4990, 'succeeded')""", (sub,))
    with pytest.raises(psycopg.errors.UniqueViolation):  # повторный webhook
        rw.execute("""INSERT INTO payments (subscription_id, provider, provider_payment_id, amount, status)
                      VALUES (%s, 'yookassa', 'pay-lc-1', 4990, 'succeeded')""", (sub,))
    rw.execute("""UPDATE subscriptions SET current_period_start = current_period_end,
                  current_period_end = current_period_end + interval '1 month' WHERE id = %s""", (sub,))
    rw.execute("UPDATE subscriptions SET status = 'past_due' WHERE id = %s", (sub,))
    with pytest.raises(psycopg.errors.CheckViolation):  # истёкшая подписка не может остаться с автопродлением
        rw.execute("UPDATE subscriptions SET status = 'expired' WHERE id = %s", (sub,))
    rw.execute("UPDATE subscriptions SET status = 'expired', auto_renew = false WHERE id = %s", (sub,))
    sub2 = one(rw, """INSERT INTO subscriptions (workspace_id, plan, status, price, current_period_start, current_period_end)
                      VALUES (%s, 'start', 'active', 4990, now(), now() + interval '1 month') RETURNING id""", ws)

    # --- деактивация: доступ закрыт, токены удалены, подписка отменена ---
    with rw.transaction():
        rw.execute("UPDATE workspaces SET status = 'deactivated', deactivated_at = now() WHERE id = %s", (ws,))
        rw.execute("UPDATE subscriptions SET status = 'canceled', canceled_at = now(), auto_renew = false WHERE id = %s", (sub2,))
        rw.execute("SELECT drop_connection_token('direct', %s, %s, 'disconnected')", (ws, dconn))
        rw.execute("SELECT drop_connection_token('metrika', %s, %s, 'disconnected')", (ws, mconn))

    # --- удаление ---
    req = one(rw, """INSERT INTO deletion_requests (workspace_id, requested_by, scope)
                     VALUES (%s, %s, 'workspace') RETURNING id""", ws, f"user:{user}")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):  # приложение не может удалить само
        rw.execute("SELECT delete_workspace_data(%s)", (ws,))

    with db("app_deleter") as dl:
        with pytest.raises(psycopg.errors.RaiseException):  # только из deletion_pending
            dl.execute("SELECT delete_workspace_data(%s)", (ws,))
        rw.execute("UPDATE workspaces SET status = 'deletion_pending' WHERE id = %s", (ws,))
        rw.execute("UPDATE deletion_requests SET status = 'deleting', started_at = now() WHERE id = %s", (req,))
        counts = one(dl, "SELECT delete_workspace_data(%s)", ws)

    assert counts["snapshots"] == 3 and counts["recommendations"] == 1 and counts["users"] == 1
    assert counts["digests"] == 1 and counts["notifications"] == 1 and counts["search_query_texts"] == 1
    assert counts["payments_anonymized"] == 1
    # проверка: по workspace не осталось ничего, кроме обезличенного платежа и отметки бесплатного аудита
    leftovers = {t: one(rw, f"SELECT count(*) FROM {t} WHERE workspace_id = %s", ws)
                 for t in ("snapshots", "audit_runs", "issues", "subscriptions", "search_query_texts",
                           "direct_connections", "metrika_connections", "sync_runs", "digests", "notifications")}
    assert leftovers == {t: 0 for t in leftovers}
    assert one(rw, "SELECT count(*) FROM workspaces WHERE id = %s", ws) == 0
    assert one(rw, "SELECT count(*) FROM users WHERE id = %s", user) == 0
    assert one(rw, "SELECT subscription_id FROM payments WHERE provider_payment_id = 'pay-lc-1'") is None
    assert one(rw, "SELECT count(*) FROM free_audit_claims WHERE direct_account_hash = %s", claim) == 1

    rw.execute("""UPDATE deletion_requests SET status = 'completed', completed_at = now(),
                  verification = %s, deleted_by = 'deleter@test' WHERE id = %s""", (Jsonb(counts), req))
    rw.close()
