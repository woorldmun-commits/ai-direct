"""DataHealth для политики (audit/policy.py): из статуса последней синхронизации — чистая функция; для снимка аудита —
snapshot_health (воркер аудита передаёт её в persist).

None на входе или в результате = «неизвестно»: политика такое не понижает (audit/policy.py)."""

from datetime import datetime, timedelta

import psycopg

from app.audit.policy import DataHealth

# ponytail: ночная синхронизация + досинхронизация в 14:00 + запас на повторы; порог уточнить на пилоте.
STALE_AFTER = timedelta(hours=36)

_NON_FINAL_STATUSES = frozenset({"queued", "running", "waiting_report", "skipped"})  # статусы sync_runs, в которых вердикта ещё (или совсем) нет


def _failed(status: str | None) -> bool | None:
    if status == "failed":
        return True
    if status == "succeeded":
        return False
    if status is None or status in _NON_FINAL_STATUSES:
        return None
    raise ValueError(f"неизвестный статус синхронизации: {status!r}")


def data_health_from_sync(status: str | None, last_sync_at: datetime | None, now: datetime,
                          stale_after: timedelta) -> DataHealth | None:
    """failed → source_failed; старше stale_after (строго) → stale. Нечего утверждать — None."""
    if stale_after < timedelta(0):
        raise ValueError("stale_after: порог не может быть отрицательным")
    if now.tzinfo is None or (last_sync_at is not None and last_sync_at.tzinfo is None):
        raise ValueError("время синхронизации — с часовым поясом")
    failed = _failed(status)
    stale = None if last_sync_at is None else now - last_sync_at > stale_after
    return None if failed is None and stale is None else DataHealth(source_failed=failed, stale=stale)


def snapshot_health(conn: psycopg.Connection, snapshot_id: int, now: datetime) -> DataHealth:
    """Отказ необязательного источника в снимке (source_failures) или упавшая последняя синхронизация аккаунта →
    source_failed; данные снимка (data_until) старше STALE_AFTER → stale."""
    failures, data_until, status = conn.execute(
        """SELECT s.source_failures, s.data_until,
                  (SELECT l.status FROM sync_runs l WHERE l.direct_account_id = r.direct_account_id
                   ORDER BY l.id DESC LIMIT 1)
           FROM snapshots s JOIN sync_runs r ON r.id = s.sync_run_id WHERE s.id = %s""", (snapshot_id,)).fetchone()
    sync = data_health_from_sync(status, data_until, now, STALE_AFTER) or DataHealth()
    return DataHealth(source_failed=True if failures else sync.source_failed, stale=sync.stale)
