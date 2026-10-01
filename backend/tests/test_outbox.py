"""Транзакционный outbox: событие существует тогда и только тогда, когда закоммичено бизнес-изменение;
доставка at-least-once с арендой, повтором и идемпотентным получателем."""

from datetime import datetime, timedelta, timezone

import pytest

from app.worker.outbox import LEASE, PublishError, _claim, deliver_pending, emit
from test_schema import chain, one  # noqa: F401 — фикстура


class Crash(BaseException):
    """Обрыв процесса: обычный `except Exception` его не ловит — как не поймал бы kill -9."""


class Receiver:
    """Получатель, идемпотентный по id события (как должен быть Telegram-/email-отправитель)."""

    def __init__(self, fail_with=None, crash_after_send=False):
        self.calls, self.delivered, self.fail_with, self.crash_after_send = [], set(), fail_with, crash_after_send

    def publish(self, event):
        self.calls.append(event.id)
        if self.fail_with:
            raise self.fail_with
        self.delivered.add(event.id)  # повтор того же id ничего не удваивает
        if self.crash_after_send:
            self.crash_after_send = False
            raise Crash


def now():
    return datetime.now(timezone.utc) + timedelta(seconds=1)


def event(rw, chain, event_type="recommendation_created") -> int:
    emit(rw, chain["ws"], event_type, "recommendation", chain["rec"], {"issue_id": chain["issue"]})
    return one(rw, "SELECT max(id) FROM outbox_events WHERE workspace_id = %s", chain["ws"])


def state(rw, event_id):
    return rw.execute("SELECT delivered_at IS NOT NULL, attempts, last_error, locked_until IS NOT NULL "
                      "FROM outbox_events WHERE id = %s", (event_id,)).fetchone()


def deliver(rw, receiver, at=None):
    return deliver_pending(rw, receiver, now=at or now(), limit=10000)


# --- событие = часть бизнес-транзакции -----------------------------------------------------------

def test_event_exists_only_if_business_transaction_commits(rw, chain):
    before = one(rw, "SELECT count(*) FROM outbox_events WHERE workspace_id = %s", chain["ws"])
    with pytest.raises(RuntimeError), rw.transaction():
        emit(rw, chain["ws"], "recommendation_created", "recommendation", chain["rec"])
        raise RuntimeError("бизнес-транзакция упала")
    assert one(rw, "SELECT count(*) FROM outbox_events WHERE workspace_id = %s", chain["ws"]) == before


def test_committed_event_is_delivered_once(rw, chain):
    eid = event(rw, chain)
    receiver = Receiver()
    deliver(rw, receiver)
    assert eid in receiver.delivered and state(rw, eid) == (True, 1, None, False)
    deliver(rw, receiver)
    assert receiver.calls.count(eid) == 1                                   # доставленное повторно не берётся


# --- падения воркера ------------------------------------------------------------------------------

def test_worker_crash_before_send_next_worker_sends_after_lease(rw, chain):
    eid = event(rw, chain)
    t = now()
    claimed = _claim(rw, t, 10000)                                          # взял и «упал», не отправив
    assert eid in [e.id for e in claimed]
    receiver = Receiver()
    deliver(rw, receiver, at=t + LEASE - timedelta(seconds=1))
    assert eid not in receiver.calls                                        # аренда ещё действует
    deliver(rw, receiver, at=t + LEASE + timedelta(seconds=1))
    assert eid in receiver.delivered and state(rw, eid)[:2] == (True, 2)


def test_crash_after_send_before_mark_is_redelivered_idempotently(rw, chain):
    eid = event(rw, chain)
    t = now()
    receiver = Receiver(crash_after_send=True)
    with pytest.raises(Crash):
        deliver(rw, receiver, at=t)
    assert state(rw, eid)[0] is False                                       # отметить не успел
    deliver(rw, receiver, at=t + LEASE + timedelta(seconds=1))
    assert receiver.calls.count(eid) == 2 and eid in receiver.delivered  # отправлено дважды, учтено один раз
    assert state(rw, eid)[0] is True                                        # доставлено; повтор — тот же id


def test_two_workers_never_take_the_same_event(rw, chain, db):
    eids = {event(rw, chain) for _ in range(5)}
    t = now()
    with db("app_rw") as other:
        first = {e.id for e in _claim(rw, t, 10000)}
        second = {e.id for e in _claim(other, t, 10000)}
    assert eids <= first and not (eids & second)


# --- ошибки получателя ----------------------------------------------------------------------------

def test_failed_delivery_is_retried_with_backoff(rw, chain):
    eid = event(rw, chain)
    t = now()
    deliver(rw, Receiver(fail_with=PublishError("telegram_unavailable")), at=t)
    delivered, attempts, error, locked = state(rw, eid)
    assert (delivered, attempts, error, locked) == (False, 1, "telegram_unavailable", False)
    early = Receiver()
    deliver(rw, early, at=t + timedelta(seconds=30))
    assert eid not in early.calls                                           # пауза перед повтором
    later = Receiver()
    deliver(rw, later, at=t + timedelta(hours=2))
    assert eid in later.delivered and state(rw, eid)[:3] == (True, 2, None)


def test_unexpected_error_marks_event_and_propagates(rw, chain):
    eid = event(rw, chain)
    with pytest.raises(ValueError):
        deliver(rw, Receiver(fail_with=ValueError("bug")))
    assert state(rw, eid)[2] == "internal_error"


def test_error_codes_not_server_text(rw, chain):
    import psycopg
    eid = event(rw, chain)
    with pytest.raises(psycopg.errors.CheckViolation):
        rw.execute("UPDATE outbox_events SET last_error = 'Telegram said: chat 12345 blocked' WHERE id = %s", (eid,))


def test_unexpected_error_releases_rest_of_batch_without_waiting_for_lease(rw, chain):
    first, rest = event(rw, chain), event(rw, chain)
    with pytest.raises(ValueError):
        deliver(rw, Receiver(fail_with=ValueError("bug")))
    # упавшее событие отмечено, остальные не держат аренду 5 минут: следующий воркер берёт их сразу
    assert state(rw, first)[3] is False and state(rw, rest)[3] is False
