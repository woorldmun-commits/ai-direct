"""Слой уведомлений: outbox — факт события, notifications — решение о сообщении. Одно событие — не больше одного
сообщения за день; «не отправлять» — строка skipped с причиной, а событие outbox всё равно доставлено."""

from datetime import datetime, timedelta, timezone

import pytest

from app.worker.notify import Notifier, run_notifications
from app.worker.outbox import OutboxEvent, emit
from test_schema import chain, one  # noqa: F401 — фикстура

NOW = datetime.now(timezone.utc) + timedelta(seconds=1)


@pytest.fixture
def ws(rw, chain):
    """Оплаченный workspace, у владельца привязан Telegram."""
    rw.execute("INSERT INTO memberships (user_id, workspace_id) VALUES (%s, %s)", (chain["user"], chain["ws"]))
    rw.execute("INSERT INTO telegram_links (user_id, chat_id) VALUES (%s, %s)", (chain["user"], 10_000 + chain["user"]))
    rw.execute("""INSERT INTO subscriptions (workspace_id, plan, status, price, current_period_start, current_period_end)
                  VALUES (%s, 'start', 'active', 4990, %s, %s)""", (chain["ws"], NOW - timedelta(10), NOW + timedelta(20)))
    return chain


def event(rw, ws, event_type="recommendation_created", aggregate_id=None, created_at=None) -> OutboxEvent:
    emit(rw, ws["ws"], event_type, "recommendation", aggregate_id or ws["rec"], {"issue_id": ws["issue"]})
    eid = one(rw, "SELECT max(id) FROM outbox_events WHERE workspace_id = %s", ws["ws"])
    if created_at:
        rw.execute("UPDATE outbox_events SET created_at = %s WHERE id = %s", (created_at, eid))
    row = rw.execute("""SELECT id, workspace_id, event_type, aggregate_type, aggregate_id, payload, created_at
                        FROM outbox_events WHERE id = %s""", (eid,)).fetchone()
    return OutboxEvent(*row)


def notifications(rw, ws):
    return rw.execute("""SELECT kind, channel, status, payload FROM notifications WHERE workspace_id = %s
                         ORDER BY id""", (ws["ws"],)).fetchall()


def test_one_event_one_notification(rw, ws):
    e = event(rw, ws)
    Notifier(rw, NOW).publish(e)
    [(kind, channel, status, payload)] = notifications(rw, ws)
    assert (kind, channel, status) == ("new_problem", "telegram", "queued")
    assert payload == {"issue_id": ws["issue"], "recommendation_id": ws["rec"], "outbox_event_id": e.id}


def test_redelivery_and_rerun_do_not_duplicate(rw, ws):
    """At-least-once: то же событие пришло повторно (в т. ч. на следующий день) — сообщение одно."""
    e = event(rw, ws)
    Notifier(rw, NOW).publish(e)
    Notifier(rw, NOW).publish(e)
    Notifier(rw, NOW + timedelta(days=1)).publish(e)  # день — по событию, не по моменту доставки
    assert len(notifications(rw, ws)) == 1


def test_two_recommendations_two_notifications(rw, ws):
    Notifier(rw, NOW).publish(event(rw, ws))
    Notifier(rw, NOW).publish(event(rw, ws, aggregate_id=ws["rec"] + 1_000_000))
    assert len(notifications(rw, ws)) == 2


def test_same_object_on_different_days_is_allowed(rw, ws):
    Notifier(rw, NOW).publish(event(rw, ws, created_at=NOW - timedelta(days=1)))
    Notifier(rw, NOW).publish(event(rw, ws, created_at=NOW))
    assert len(notifications(rw, ws)) == 2


def test_same_object_same_day_is_deduplicated(rw, ws):
    Notifier(rw, NOW).publish(event(rw, ws))
    Notifier(rw, NOW).publish(event(rw, ws))  # другое событие того же объекта в тот же день
    assert len(notifications(rw, ws)) == 1


@pytest.mark.parametrize("setup, reason", [
    ("UPDATE subscriptions SET status = 'expired' WHERE workspace_id = %(ws)s", "subscription_inactive"),
    ("DELETE FROM telegram_links WHERE user_id = %(user)s", "no_recipient"),
])
def test_not_sent_is_skipped_with_reason(rw, ws, setup, reason):
    rw.execute(setup, ws)
    Notifier(rw, NOW).publish(event(rw, ws))
    [(_, _, status, payload)] = notifications(rw, ws)
    assert status == "skipped" and payload["skip_reason"] == reason  # в очередь отправки не попадает


def test_event_without_message_creates_nothing(rw, ws):
    Notifier(rw, NOW).publish(event(rw, ws, "recommendation_seen_again"))
    assert notifications(rw, ws) == []


def test_outbox_event_is_delivered_whatever_the_decision(rw, ws):
    """Решение слоя уведомлений (отправить / пропустить / не нужно) не мешает outbox: событие доставлено и хранится."""
    rw.execute("UPDATE subscriptions SET status = 'expired' WHERE workspace_id = %s", (ws["ws"],))
    ids = [event(rw, ws).id, event(rw, ws, "recommendation_resolved").id]
    run_notifications(rw, now=datetime.now(timezone.utc) + timedelta(seconds=1), limit=10_000)  # события уже созданы
    rows = rw.execute("SELECT delivered_at IS NOT NULL FROM outbox_events WHERE id = ANY(%s)", (ids,)).fetchall()
    assert rows == [(True,), (True,)]
    assert [n[2] for n in notifications(rw, ws)] == ["skipped"]
