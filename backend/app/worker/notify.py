"""Слой уведомлений — получатель outbox (ARCHITECTURE.md §5.1). Outbox хранит факт «событие произошло»; здесь
решается, нужно ли сообщение, есть ли кому и куда его слать и не было ли его уже в этот день.

Итог по событию — одна строка notifications: queued (отправит Telegram-отправитель) или skipped с причиной
(guard NOTIFY, нет получателя), либо ничего, если событие сообщений не порождает. Любое из этих решений —
успешная доставка события в этот слой: outbox отмечает его доставленным, но не удаляет.

Доставка outbox — системная задача по многим workspace: соединение роли app_system (RLS не фильтрует по workspace,
schema.sql «Изоляция арендаторов»).

Идемпотентность — dedup_key = kind:workspace:object:день события (по часовому поясу данных): повторная доставка
того же события (at-least-once) и повторный запуск не создают второе сообщение."""

from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from app.worker.guard import Skip, Task, guard, load_state
from app.worker.measure import DATA_TIMEZONE
from app.worker.outbox import OutboxEvent, deliver_pending

# Какие события порождают сообщение. Уточнения цифр — из сравнения с дайджестом, не из seen_again (PRD §3);
# критические события подключений в outbox пока не пишутся.
KINDS = {"recommendation_created": "new_problem"}
CHANNEL = "telegram"


class Notifier:
    """Publisher для deliver_pending. now — момент запуска: guard проверяет состояние на момент выполнения."""

    def __init__(self, conn: psycopg.Connection, now: datetime):
        self.conn, self.now = conn, now

    def publish(self, event: OutboxEvent) -> None:
        kind = KINDS.get(event.event_type)
        if kind is None:
            return
        day = event.created_at.astimezone(DATA_TIMEZONE).date()
        dedup_key = f"{kind}:{event.workspace_id}:{event.aggregate_type}:{event.aggregate_id}:{day.isoformat()}"
        with self.conn.transaction():
            skip_reason = self._skip_reason(event.workspace_id)
            payload = {**event.payload, "outbox_event_id": event.id, f"{event.aggregate_type}_id": event.aggregate_id}
            if skip_reason:
                payload["skip_reason"] = skip_reason
            self.conn.execute("""INSERT INTO notifications (workspace_id, kind, channel, dedup_key, payload, status)
                                 VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (dedup_key) DO NOTHING""",
                              (event.workspace_id, kind, CHANNEL, dedup_key, Jsonb(payload),
                               "skipped" if skip_reason else "queued"))

    def _skip_reason(self, workspace_id: int) -> str | None:
        if isinstance(d := guard(Task.NOTIFY, load_state(self.conn, workspace_id, None, self.now)), Skip):
            return d.reason
        # Получатели — все, у кого есть доступ к workspace (owner/admin организации и участники workspace):
        # та же точка проверки, что и для входа в workspace. Деактивированных представление не возвращает.
        has_recipient = self.conn.execute("""SELECT 1 FROM effective_workspace_access a
                                             JOIN telegram_links t ON t.user_id = a.user_id
                                             WHERE a.workspace_id = %s LIMIT 1""", (workspace_id,)).fetchone()
        return None if has_recipient else "no_recipient"


def run_notifications(conn: psycopg.Connection, *, now: datetime, limit: int = 100) -> int:
    """Один проход: готовые события outbox → notifications. Возвращает число обработанных событий."""
    return deliver_pending(conn, Notifier(conn, now), now=now, limit=limit)
