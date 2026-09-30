"""Транзакционный outbox: emit() — внутри бизнес-транзакции (событие появится только вместе с её COMMIT);
deliver_pending() — после, отдельным воркером. Доставка at-least-once: воркер может упасть между отправкой и
отметкой — получатель (Publisher) обязан быть идемпотентным по event.id.

Захват — короткая транзакция с FOR UPDATE SKIP LOCKED и арендой (locked_until): два воркера не берут одно событие,
а упавший воркер не держит событие вечно — аренда истекает, событие забирает следующий."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Protocol

import psycopg
from psycopg.types.json import Jsonb

LEASE = timedelta(minutes=5)
MAX_BACKOFF = timedelta(hours=1)


@dataclass(frozen=True)
class OutboxEvent:
    id: int  # ключ идемпотентности для получателя
    workspace_id: int
    event_type: str
    aggregate_type: str
    aggregate_id: int
    payload: Mapping


class PublishError(Exception):
    """Получатель не принял событие. code — в last_error (только код, без текста сервера)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Publisher(Protocol):
    def publish(self, event: OutboxEvent) -> None: ...


def emit(conn: psycopg.Connection, workspace_id: int, event_type: str, aggregate_type: str, aggregate_id: int,
         payload: Mapping | None = None) -> None:
    """Вызывать внутри транзакции бизнес-изменения. payload — только ID и числа."""
    conn.execute("""INSERT INTO outbox_events (workspace_id, event_type, aggregate_type, aggregate_id, payload)
                    VALUES (%s, %s, %s, %s, %s)""",
                 (workspace_id, event_type, aggregate_type, aggregate_id, Jsonb(dict(payload or {}))))


def _claim(conn: psycopg.Connection, now: datetime, limit: int) -> list[OutboxEvent]:
    with conn.transaction():
        rows = conn.execute("""SELECT id, workspace_id, event_type, aggregate_type, aggregate_id, payload
                               FROM outbox_events
                               WHERE delivered_at IS NULL AND available_at <= %s
                                 AND (locked_until IS NULL OR locked_until < %s)
                               ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED""", (now, now, limit)).fetchall()
        if rows:
            conn.execute("UPDATE outbox_events SET locked_until = %s, attempts = attempts + 1 WHERE id = ANY(%s)",
                         (now + LEASE, [r[0] for r in rows]))
    return [OutboxEvent(*r) for r in rows]


def _backoff(attempts: int) -> timedelta:
    return min(timedelta(minutes=2 ** min(attempts, 10)), MAX_BACKOFF)


def deliver_pending(conn: psycopg.Connection, publisher: Publisher, *, now: datetime, limit: int = 100) -> int:
    """Доставить готовые события. Возвращает число доставленных. Ошибка получателя — повтор с растущей паузой
    (failed не окончательный); непредвиденная ошибка отмечается internal_error и пробрасывается."""
    assert conn.autocommit, "захват и отметка — отдельные короткие транзакции: нужен autocommit"
    delivered = 0
    for event in _claim(conn, now, limit):
        try:
            publisher.publish(event)  # вне транзакции БД
        except PublishError as e:
            _fail(conn, event.id, e.code, now)
            continue
        except Exception:
            _fail(conn, event.id, "internal_error", now)
            raise
        conn.execute("""UPDATE outbox_events SET delivered_at = %s, locked_until = NULL, last_error = NULL
                        WHERE id = %s""", (now, event.id))
        delivered += 1
    return delivered


def _fail(conn: psycopg.Connection, event_id: int, code: str, now: datetime) -> None:
    attempts = conn.execute("SELECT attempts FROM outbox_events WHERE id = %s", (event_id,)).fetchone()[0]
    conn.execute("""UPDATE outbox_events SET locked_until = NULL, last_error = %s, available_at = %s WHERE id = %s""",
                 (code, now + _backoff(attempts), event_id))
