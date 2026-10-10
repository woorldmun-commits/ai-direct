"""Мониторинг: свежесть синхронизаций, счётчики sync_run по статусам и GET /ops/health (токен, 503 при stale, без ПД)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.api import create_app
from app.obs.health import freshness, sync_health
from test_api_support import client_for, dsn, settings
from test_schema import chain, one  # noqa: F401 — фикстура

NOW = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
DAY = timedelta(hours=26)


@pytest.mark.parametrize("last, expected", [
    (None, "no_data"), (NOW - timedelta(hours=1), "ok"), (NOW - DAY, "ok"), (NOW - DAY - timedelta(seconds=1), "stale"),
])
def test_freshness(last, expected):
    assert freshness(last, NOW, DAY) == expected


def test_sync_health_counts_by_status(rw, chain):
    now = datetime.now(timezone.utc)
    before = sync_health(rw, now=now, stale_after=DAY).runs_24h
    rw.execute("""INSERT INTO sync_runs (workspace_id, direct_account_id, kind, status, finished_at, error_code)
                  VALUES (%(ws)s, %(acc)s, 'scheduled', 'failed', now(), 'access_denied'),
                         (%(ws)s, %(acc)s, 'scheduled', 'failed', now(), 'invalid_request'),
                         (%(ws)s, %(acc)s, 'scheduled', 'queued', NULL, NULL)""",
               {"ws": chain["ws"], "acc": chain["account"]})
    health = sync_health(rw, now=now, stale_after=DAY)
    assert health.runs_24h["failed"] == before.get("failed", 0) + 2
    assert health.runs_24h["queued"] == before.get("queued", 0) + 1
    assert health.status == "ok" and health.last_success_at is not None  # chain: успешный запуск только что


@pytest.fixture
def ops(db, monkeypatch):
    monkeypatch.setenv("OPS_TOKEN", "test-ops-token")
    monkeypatch.setenv("OPS_DATABASE_URL", dsn(db, "app_system"))
    with client_for(create_app(settings(db))) as c:
        yield c


AUTH = {"Authorization": "Bearer test-ops-token"}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "test-ops-token"}])
def test_ops_health_requires_token(ops, headers):
    assert ops.get("/api/v1/ops/health", headers=headers).status_code == 404


def test_ops_health_hidden_without_configured_token(ops, monkeypatch):
    monkeypatch.delenv("OPS_TOKEN")
    assert ops.get("/api/v1/ops/health", headers={"Authorization": "Bearer "}).status_code == 404


def test_ops_health_reports_aggregates_only(ops, rw, chain):
    r = ops.get("/api/v1/ops/health", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["stale_after_hours"] == 26 and body["runs_24h"]["succeeded"] >= 1
    assert set(body) == {"status", "last_success_at", "hours_since_success", "stale_after_hours", "runs_24h"}
    login = one(rw, """SELECT c.yandex_login FROM direct_accounts a JOIN direct_connections c
                       ON c.id = a.direct_connection_id WHERE a.id = %s""", chain["account"])
    assert login not in r.text


def test_ops_health_stale_is_503(ops, rw, chain, monkeypatch):
    monkeypatch.setenv("OPS_SYNC_STALE_HOURS", "0.000001")  # любая синхронизация «старая»
    r = ops.get("/api/v1/ops/health", headers=AUTH)
    assert r.status_code == 503 and r.json()["status"] == "stale"


def test_ops_health_db_unavailable(ops, monkeypatch):
    monkeypatch.setenv("OPS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    r = ops.get("/api/v1/ops/health", headers=AUTH)
    assert r.status_code == 503 and r.json() == {"status": "unavailable"}
