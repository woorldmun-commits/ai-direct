"""DataHealth из статуса последней синхронизации — чистая функция. Подключение к воркеру — отдельный шаг (PR-2b).

None на входе или в результате = «неизвестно»: политика такое не понижает (audit/policy.py)."""

from datetime import datetime, timedelta

from app.audit.policy import DataHealth

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
