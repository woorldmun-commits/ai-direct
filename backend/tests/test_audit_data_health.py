"""Состояние данных в конвейере аудита: отказ источника и устаревшие данные доходят до safety_policy@2 и только
понижают уровень действия (audit/data_health.py → persist → findings.action_level)."""

from datetime import timedelta

import pytest

from app.audit.policy import LEVELS, DataHealth, decide_v2
from app.sources.metrika import MetrikaFixture
import test_rule_high_cpa as hc
from test_rules_v2 import hc_view, v2
from test_direct_sync import root  # noqa: F401 — фикстура
from test_metrika_sync import metrika  # noqa: F401 — фикстура
from test_schema import chain, one  # noqa: F401 — фикстура
from test_worker_audit import audit, fresh, sync  # noqa: F401 — fresh: autouse-фикстура
from test_worker_sync import NOW, new_run, work, ws  # noqa: F401 — ws: фикстура

SOURCE_REASONS = {"source_failed", "source_stale"}


@pytest.fixture(autouse=True)
def target(rw, ws):
    """Целевой CPA задан: кандидат — decrease_bid (change), есть что понижать."""
    rw.execute("INSERT INTO workspace_settings (workspace_id, target_cpa) VALUES (%s, 3000)", (ws["ws"],))


def decision(rw, audit_run_id):
    return rw.execute("""SELECT candidate_level, action_level, policy_reasons FROM findings
                         WHERE audit_run_id = %s AND rule_version = 'high_cpa_target@2'""",
                      (audit_run_id,)).fetchone()


def test_fresh_data_keeps_level(rw, ws):
    sync(rw, ws)
    candidate, level, reasons = decision(rw, audit(rw, ws).audit_run_id)
    assert (candidate, level) == ("change", "review") and not SOURCE_REASONS & set(reasons)


def test_metrika_failure_lowers_level(rw, ws, tmp_path):
    assert work(rw, ws, new_run(rw, ws), metrika_source=MetrikaFixture(tmp_path / "none")).snapshot_id
    candidate, level, reasons = decision(rw, audit(rw, ws).audit_run_id)
    assert (candidate, level) == ("change", "inspect_only") and "source_failed" in reasons


def test_failed_last_sync_lowers_level(rw, ws):
    """Снимок на cutoff есть, но последняя синхронизация аккаунта упала: источник сейчас отказывает."""
    sync(rw, ws)
    rw.execute("""INSERT INTO sync_runs (workspace_id, direct_account_id, kind, status, started_at, finished_at,
                                         error_code)
                  VALUES (%s, %s, 'resync', 'failed', now(), now(), 'invalid_request')""", (ws["ws"], ws["account"]))
    _, level, reasons = decision(rw, audit(rw, ws).audit_run_id)
    assert level == "inspect_only" and "source_failed" in reasons


def test_stale_data_lowers_level(rw, ws):
    sync(rw, ws)
    _, level, reasons = decision(rw, audit(rw, ws, now=NOW + timedelta(days=3)).audit_run_id)
    assert level == "inspect_only" and "source_stale" in reasons


@pytest.mark.parametrize("conv", [1, 3, 12, 50])
@pytest.mark.parametrize("health", [DataHealth(f, s) for f in (None, False, True) for s in (None, False, True)])
def test_health_never_raises_level(conv, health):
    f = hc.only(v2(hc_view(eval_cost=5250 * conv, eval_conv=conv), hc.TARGET))
    assert LEVELS.index(decide_v2(f, health).level) <= LEVELS.index(decide_v2(f).level)
