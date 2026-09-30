"""Состав аудита workspace — единственное место, где решается, какие аккаунты и снимки в него входят.
Правила снимки не ищут: они получают готовые SnapshotView.

Для каждого выбранного аккаунта Директа: доступен (та же проверка, что в guard) → последний complete снимок
ровно на data_cutoff. Снимки разных дней не смешиваются: аккаунт без снимка на cutoff исключается с причиной,
а не подменяется вчерашним. Недоступный аккаунт — тоже исключение с причиной, а не NOT_ENOUGH_DATA в каждом правиле."""

from dataclasses import dataclass
from datetime import date, datetime

import psycopg

from app.worker.guard import direct_unavailable, load_state


@dataclass(frozen=True)
class Included:
    account_id: int
    snapshot_id: int


@dataclass(frozen=True)
class Excluded:
    account_id: int
    reason: str   # direct_unavailable · no_snapshot_for_cutoff
    detail: str   # access_denied, token_expired… · дата cutoff

    def to_json(self) -> dict:
        return {"account": self.account_id, "reason": self.reason, "detail": self.detail}


@dataclass(frozen=True)
class Selection:
    data_cutoff: date
    included: tuple[Included, ...]
    excluded: tuple[Excluded, ...]


def _latest_snapshot(conn: psycopg.Connection, workspace_id: int, account_id: int, cutoff: date) -> int | None:
    row = conn.execute("""SELECT s.id FROM snapshots s JOIN sync_runs r ON r.id = s.sync_run_id
                          WHERE s.workspace_id = %s AND r.direct_account_id = %s
                            AND s.status = 'complete' AND s.period_to = %s
                          ORDER BY s.sealed_at DESC, s.id DESC LIMIT 1""",
                       (workspace_id, account_id, cutoff)).fetchone()
    return row[0] if row else None


def select_accounts(conn: psycopg.Connection, workspace_id: int, data_cutoff: date, now: datetime) -> Selection:
    accounts = [r[0] for r in conn.execute("""SELECT a.id FROM direct_accounts a
                                              JOIN direct_connections c ON c.id = a.direct_connection_id
                                              WHERE c.workspace_id = %s AND a.is_selected ORDER BY a.id""",
                                           (workspace_id,)).fetchall()]
    included, excluded = [], []
    for account_id in accounts:
        if detail := direct_unavailable(load_state(conn, workspace_id, account_id, now)):
            excluded.append(Excluded(account_id, "direct_unavailable", detail))
        elif (snapshot_id := _latest_snapshot(conn, workspace_id, account_id, data_cutoff)) is None:
            excluded.append(Excluded(account_id, "no_snapshot_for_cutoff", data_cutoff.isoformat()))
        else:
            included.append(Included(account_id, snapshot_id))
    return Selection(data_cutoff, tuple(included), tuple(excluded))
