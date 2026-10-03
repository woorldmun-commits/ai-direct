"""Числа в шаблонных объяснениях — как в ValueView фронтенда (frontend/lib/value.ts: formatAmount): без округления
(раньше f"{x:,.0f}" округлял банковски: 2 500,50 → «2 500», 2 501,50 → «2 502»), копейки — только если они есть."""

from decimal import Decimal

import pytest

from app.audit.templates import _rub


@pytest.mark.parametrize("amount, text", [
    ("2500.50", "2 500,50"),
    ("2501.50", "2 501,50"),
    ("2500.00", "2 500"),
    ("2500", "2 500"),
    ("1234567.05", "1 234 567,05"),
    ("0.5", "0,50"),
    ("150", "150"),
    ("0", "0"),
])
def test_rub_keeps_kopecks_without_rounding(amount, text):
    assert _rub(Decimal(amount)) == text
