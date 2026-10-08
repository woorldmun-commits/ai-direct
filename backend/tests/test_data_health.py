"""DataHealth из статуса синхронизации: чистая функция, без проводки воркера (PR-2b)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.audit.data_health import data_health_from_sync
from app.audit.policy import DataHealth

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
DAY = timedelta(hours=24)


def test_failed_status_marks_source_failed():
    h = data_health_from_sync("failed", NOW - timedelta(hours=1), NOW, DAY)
    assert h == DataHealth(source_failed=True, stale=False)


def test_failed_without_last_sync_keeps_stale_unknown():
    assert data_health_from_sync("failed", None, NOW, DAY) == DataHealth(source_failed=True, stale=None)


def test_old_sync_is_stale():
    h = data_health_from_sync("succeeded", NOW - DAY - timedelta(seconds=1), NOW, DAY)
    assert h == DataHealth(source_failed=False, stale=True)


def test_threshold_boundary_is_not_stale():
    assert data_health_from_sync("succeeded", NOW - DAY, NOW, DAY) == DataHealth(False, False)


def test_fresh_success_is_known_healthy():
    assert data_health_from_sync("succeeded", NOW - timedelta(hours=1), NOW, DAY) == DataHealth(False, False)


@pytest.mark.parametrize("status", [None, "queued", "running", "waiting_report", "skipped"])
def test_unknown_everything_returns_none(status):
    assert data_health_from_sync(status, None, NOW, DAY) is None


def test_non_terminal_status_still_reports_staleness():
    assert data_health_from_sync("running", NOW - 3 * DAY, NOW, DAY) == DataHealth(source_failed=None, stale=True)


def test_unknown_status_string_raises():
    with pytest.raises(ValueError):
        data_health_from_sync("weird", NOW, NOW, DAY)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        data_health_from_sync("succeeded", datetime(2026, 10, 8), NOW, DAY)


def test_future_last_sync_is_not_stale():
    assert data_health_from_sync("succeeded", NOW + timedelta(hours=1), NOW, DAY) == DataHealth(False, False)
