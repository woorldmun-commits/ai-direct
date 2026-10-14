"""Флаг «целевой CPA введён с НДС» из workspace_settings доходит до правил и замораживается в audit_run.settings."""

from decimal import Decimal

import pytest

from app.worker.audit import _settings
from test_schema import chain  # noqa: F401 — фикстура


@pytest.mark.parametrize("includes_vat", [True, False])
def test_vat_flag_reaches_audit_settings(rw, chain, includes_vat):
    rw.execute("""INSERT INTO workspace_settings (workspace_id, target_cpa, target_cpa_includes_vat) VALUES (%s, 1000, %s)
                  ON CONFLICT (workspace_id) DO UPDATE SET target_cpa = 1000,
                  target_cpa_includes_vat = EXCLUDED.target_cpa_includes_vat""", (chain["ws"], includes_vat))
    settings, frozen = _settings(rw, chain["ws"])
    assert settings.target_cpa == Decimal(1000) and settings.target_cpa_includes_vat is includes_vat
    assert frozen["target_cpa_includes_vat"] is includes_vat


def test_without_settings_row_keeps_default(rw):
    settings, frozen = _settings(rw, 10**12)  # workspace без строки настроек
    assert settings.target_cpa is None and settings.target_cpa_includes_vat is True
