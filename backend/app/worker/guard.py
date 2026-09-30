"""Единственная точка допуска фоновых задач (DATA_MODEL.md §9.1). Декларативная таблица: задача → проверки по порядку;
первая не пройденная → SKIP с причиной. Состояние загружается в момент выполнения, а не постановки в очередь.

Guard решает только «можно ли по состоянию» (ALLOW / SKIP). RETRY — результат исполнения (retryIn, временная ошибка API, сбой БД),
его возвращает воркер, а не guard."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable

import psycopg


RENEWAL_GRACE = timedelta(days=3)  # past_due: 3 дня на оплату (DATA_MODEL.md §8.4)


class Task(str, Enum):
    SYNC = "sync"                  # плановая синхронизация (+ аудит)
    RECHECK = "recheck"            # проверка доступа: разрешена и для недоступного аккаунта
    AUDIT = "audit"
    MEASURE = "measure"            # verify через 7 дней
    NOTIFY = "notify"
    NOTIFY_BILLING = "notify_billing"
    DELETE = "delete"


@dataclass(frozen=True)
class State:
    workspace_status: str | None          # None: workspace уже удалён
    subscription_status: str | None       # None: подписки не было
    subscription_period_end: datetime | None
    direct_status: str | None             # статус подключения Директа; None — не подключён
    direct_account_status: str | None     # active · unavailable
    direct_unavailable_reason: str | None  # access_denied · account_not_found · api_restricted
    now: datetime

    @property
    def paid(self) -> bool:
        """Paid (§8.4): canceled — до конца оплаченного периода; active · past_due — до конца периода плюс грейс
        на продление. Верхняя граница нужна и для active: если задача продления/истечения опоздала или упала,
        доступ не должен остаться бессрочным."""
        if self.subscription_period_end is None:
            return False
        if self.subscription_status in ("active", "past_due"):
            return self.now < self.subscription_period_end + RENEWAL_GRACE
        return (self.subscription_status == "canceled" and self.subscription_period_end is not None
                and self.now < self.subscription_period_end)


@dataclass(frozen=True)
class Allow:
    pass


@dataclass(frozen=True)
class Skip:
    reason: str               # по нему guard принимает решение
    detail: str | None = None  # что именно: token_expired, access_denied… — для UI («переподключить», «выдать доступ»)


Decision = Allow | Skip
@dataclass(frozen=True)
class Check:
    reason: str
    allowed: Callable[[State], bool]
    detail: Callable[[State], str | None] = lambda s: None


def _direct_detail(s: State) -> str:
    """Подключение важнее аккаунта: с истёкшим токеном неважно, есть ли доступ к конкретному аккаунту."""
    if s.direct_status is None:
        return "not_connected"
    if s.direct_status != "connected":
        return s.direct_status  # token_expired · token_revoked · permission_missing · api_error · disconnected
    return s.direct_unavailable_reason or "unavailable"


_ACTIVE = Check("workspace_inactive", lambda s: s.workspace_status == "active", lambda s: s.workspace_status)
_PAID = Check("subscription_inactive", lambda s: s.paid, lambda s: s.subscription_status or "none")
_DIRECT = Check("direct_unavailable", lambda s: s.direct_status == "connected" and s.direct_account_status == "active",
                _direct_detail)
# recheck нужен именно недоступному аккаунту; не поможет только отсутствию токена — там нужен новый OAuth
_HAS_TOKEN = Check("direct_unavailable", lambda s: s.direct_status not in (None, "token_revoked", "disconnected"),
                   _direct_detail)
_NOT_DELETED = Check("workspace_deleted", lambda s: s.workspace_status is not None)

RULES: dict[Task, tuple[Check, ...]] = {
    Task.SYNC: (_ACTIVE, _PAID, _DIRECT),
    Task.RECHECK: (_ACTIVE, _HAS_TOKEN),
    Task.AUDIT: (_ACTIVE, _PAID),                     # аудит читает уже записанный снимок, API не трогает
    Task.MEASURE: (_ACTIVE, _PAID),                   # замер читает снимки, API не трогает
    Task.NOTIFY: (_ACTIVE, _PAID),
    Task.NOTIFY_BILLING: (_ACTIVE,),                  # о платеже сообщаем и без активной подписки
    Task.DELETE: (_NOT_DELETED,),
}


def direct_unavailable(state: State) -> str | None:
    """Та же проверка Директа, что в guard: None — доступен, иначе причина (для состава аудита)."""
    return None if _DIRECT.allowed(state) else _DIRECT.detail(state)


def guard(task: Task, state: State) -> Decision:
    for check in RULES[task]:
        if not check.allowed(state):
            return Skip(check.reason, check.detail(state))
    return Allow()


def load_state(conn: psycopg.Connection, workspace_id: int, direct_account_id: int | None,
               now: datetime) -> State:
    """Текущее состояние из БД — всегда заново, никогда из параметров задачи."""
    if now.tzinfo is None:
        raise ValueError("now: нужна дата с часовым поясом — сравнивается с timestamptz из БД")
    ws = conn.execute("SELECT status FROM workspaces WHERE id = %s", (workspace_id,)).fetchone()
    # Приоритет: действующая на сейчас (active · past_due · canceled, период уже начался) > последняя по окончании
    # периода > нет. «expired» и «none» — разные действия в UI («продлить» / «оформить»).
    sub = conn.execute("""SELECT status, current_period_end FROM subscriptions WHERE workspace_id = %s
                          ORDER BY (status IN ('active', 'past_due', 'canceled') AND current_period_start <= %s) DESC,
                                   current_period_end DESC, id DESC
                          LIMIT 1""", (workspace_id, now)).fetchone()
    direct = conn.execute("""SELECT c.status, a.status, a.unavailable_reason FROM direct_accounts a
                             JOIN direct_connections c ON c.id = a.direct_connection_id
                             WHERE a.id = %s AND c.workspace_id = %s""",
                          (direct_account_id, workspace_id)).fetchone() if direct_account_id else None
    return State(workspace_status=ws[0] if ws else None,
                 subscription_status=sub[0] if sub else None, subscription_period_end=sub[1] if sub else None,
                 direct_status=direct[0] if direct else None, direct_account_status=direct[1] if direct else None,
                 direct_unavailable_reason=direct[2] if direct else None, now=now)
