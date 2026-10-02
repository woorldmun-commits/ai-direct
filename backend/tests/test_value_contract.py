"""Контракт Value: один набор примеров проходит и через Pydantic, и через SQL value_is_valid — вердикты обязаны совпасть.
Прямой путь: API → Pydantic → БД. Обратный: БД → SQL-проверка → Pydantic."""

from datetime import date
from decimal import Decimal

import pytest
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.audit.values import to_value
from app.contract import Value
from app.rules.domain import Fact, Window

BASE = {
    "amount": "12400.00", "unit": "rub", "source": "yandex_direct",
    "period_from": "2026-09-22", "period_to": "2026-09-28",
    "calculation_type": "actual", "data_status": "complete", "data_sufficiency": "sufficient",
    "snapshot_id": 1, "rule_version": None, "formula": None,
}
UNAVAILABLE = {"amount": None, "calculation_type": "unavailable", "data_sufficiency": "insufficient"}


def v(**kw) -> dict:
    return {**BASE, **kw}


def without(*keys) -> dict:
    return {k: x for k, x in BASE.items() if k not in keys}


CASES = [
    # --- валидные ---
    ("actual", v(), True),
    ("amount как число", v(amount=12400), True),
    ("amount дробное число", v(amount=12400.5), True),
    ("отрицательный amount", v(amount="-5.00"), True),
    ("estimated с формулой", v(calculation_type="estimated", formula="a / b"), True),
    ("unavailable", v(**UNAVAILABLE), True),
    ("необязательные ключи опущены", without("rule_version", "formula"), True),
    ("rule_version задан", v(rule_version="high_cpa_target@3"), True),
    ("составной source", v(source="yandex_direct+user_input"), True),
    ("period_from = period_to", v(period_from="2026-09-28"), True),
    ("partial", v(data_status="partial"), True),
    # --- инварианты ---
    ("actual без числа", v(amount=None), False),
    ("unavailable с числом", v(calculation_type="unavailable", data_sufficiency="insufficient"), False),
    ("insufficient при actual", v(data_sufficiency="insufficient"), False),
    ("unavailable при sufficient", v(**{**UNAVAILABLE, "data_sufficiency": "sufficient"}), False),
    ("estimated без формулы", v(calculation_type="estimated"), False),
    ("estimated с пустой формулой", v(calculation_type="estimated", formula=""), False),
    ("период задом наперёд", v(period_from="2026-09-29"), False),
    # --- словари значений ---
    ("неизвестный unit", v(unit="usd"), False),
    ("неизвестный source", v(source="google_ads"), False),
    ("пустой source", v(source=""), False),
    ("source с неизвестной частью", v(source="yandex_direct+crm"), False),
    ("неизвестный calculation_type", v(calculation_type="guess"), False),
    ("неизвестный data_status", v(data_status="stale"), False),
    ("неизвестный data_sufficiency", v(data_sufficiency="maybe"), False),
    ("кривой rule_version", v(rule_version="high_cpa"), False),
    # --- null там, где запрещён ---
    ("source = null", v(source=None), False),
    ("unit = null", v(unit=None), False),
    ("period_from = null", v(period_from=None), False),
    ("snapshot_id = null", v(snapshot_id=None), False),
    ("data_status = null", v(data_status=None), False),
    # --- неверный тип ---
    ("amount не число", v(amount="abc"), False),
    ("amount bool", v(amount=True), False),
    ("amount объект", v(amount={"x": 1}), False),
    ("snapshot_id строкой", v(snapshot_id="1"), False),
    ("snapshot_id дробный", v(snapshot_id=1.5), False),
    ("snapshot_id bool", v(snapshot_id=True), False),
    ("дата не строка", v(period_from=20260922), False),
    ("дата не ISO", v(period_from="22.09.2026"), False),
    ("несуществующая дата", v(period_from="2026-02-30"), False),
    ("formula числом", v(formula=5), False),
    ("rule_version числом", v(rule_version=3), False),
    ("не объект", [BASE], False),
    ("строка вместо объекта", "value", False),
    # --- обязательные и лишние поля ---
    ("нет snapshot_id", without("snapshot_id"), False),
    ("нет amount", without("amount"), False),
    ("нет unit", without("unit"), False),
    ("лишнее поле", v(currency="RUB"), False),
    # --- регрессии из ревью: Python принимал, SQL отвергал ---
    ("source с переводом строки", v(source="yandex_direct\n"), False),
    ("rule_version с переводом строки", v(rule_version="a@1\n"), False),
    ("amount с переводом строки", v(amount="5\n"), False),
    ("amount арабской цифрой", v(amount="٣"), False),
    ("дата арабскими цифрами", v(period_from="٢٠٢٦-09-22"), False),
    ("отрицательный snapshot_id", v(snapshot_id=-1), False),
]
IDS = [c[0] for c in CASES]


def pydantic_accepts(payload) -> bool:
    try:
        Value.model_validate(payload)
    except ValidationError:
        return False
    return True


@pytest.mark.parametrize("name, payload, ok", CASES, ids=IDS)
def test_pydantic_verdict(name, payload, ok):
    assert pydantic_accepts(payload) is ok


@pytest.mark.parametrize("name, payload, ok", CASES, ids=IDS)
def test_sql_verdict(rw, name, payload, ok):
    got = rw.execute("SELECT value_is_valid(%s)", (Jsonb(payload),)).fetchone()[0]
    assert got is ok


@pytest.mark.parametrize("name, payload", [(n, p) for n, p, ok in CASES if ok], ids=[n for n, _, ok in CASES if ok])
def test_roundtrip_api_to_db_and_back(rw, name, payload):
    """API → Pydantic → jsonb → SQL-проверка → Pydantic: значение не меняется и остаётся валидным."""
    model = Value.model_validate(payload)
    dumped = model.model_dump(mode="json")
    stored = rw.execute("SELECT %s::jsonb, value_is_valid(%s)", (Jsonb(dumped), Jsonb(dumped))).fetchone()
    assert stored[1] is True
    assert Value.model_validate(stored[0]) == model


def test_evidence_and_arrays_reject_any_bad_member(rw):
    bad = v(amount=None)
    assert rw.execute("SELECT evidence_is_valid(%s)", (Jsonb({"a": BASE, "b": bad}),)).fetchone()[0] is False
    assert rw.execute("SELECT values_are_valid(%s)", (Jsonb([BASE, bad]),)).fetchone()[0] is False
    assert rw.execute("SELECT evidence_is_valid(%s)", (Jsonb({"a": BASE}),)).fetchone()[0] is True


def test_decimal_in_exponent_form_is_stored_positionally(rw):
    """Decimal("1E+2") валиден (это 100), но в jsonb должен уйти как «100», а не «1E+2»."""
    dumped = Value.model_validate(v(amount=Decimal("1E+2"))).model_dump(mode="json")
    assert dumped["amount"] == "100"
    assert rw.execute("SELECT value_is_valid(%s)", (Jsonb(dumped),)).fetchone()[0] is True


# --- Fact правила → Value: unavailable выражается с теми же инвариантами --------------------------------

WINDOW = Window(date(2026, 9, 24), date(2026, 9, 30))


def test_unavailable_fact_becomes_valid_unavailable_value(rw):
    fact = Fact.unavailable("rub", "yandex_direct+yandex_metrika", WINDOW)
    value = to_value(fact, 1, WINDOW.date_from, "zero_conv_campaign@1")
    assert (value.amount, value.calculation_type, value.data_sufficiency) == (None, "unavailable", "insufficient")
    dumped = value.model_dump(mode="json")
    assert rw.execute("SELECT value_is_valid(%s)", (Jsonb(dumped),)).fetchone()[0] is True


@pytest.mark.parametrize("kw", [
    {"amount": None},                                                   # нет числа — но не unavailable
    {"amount": Decimal(1), "calculation_type": "unavailable"},          # unavailable с числом
    {"amount": Decimal(1), "calculation_type": "estimated"},            # estimated без формулы
])
def test_fact_keeps_value_invariants(kw):
    with pytest.raises(ValueError):
        Fact(unit="rub", source="yandex_direct", period=WINDOW, **{"calculation_type": "actual", **kw})
