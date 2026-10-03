"""zero_conv_placements@1 — площадки РСЯ без конверсий: пороги на границах, досчёт конверсий, ориентир CPA,
доказательства для объединения расхода без двойного учёта, golden-кейсы (evals/cases/zero_conv_placements/)."""

import dataclasses
import json
import re
from datetime import date, timedelta
from decimal import Decimal

import pytest
from psycopg.types.json import Jsonb

from app.audit.policy import decide
from app.audit.templates import explain
from app.audit.values import to_value
from app.contract import Value
from app.rules.domain import (DIRECT_CONVERSIONS, DIRECT_PLACEMENTS, AuditSettings, CampaignDay, ExposureBasis, NotEnoughData,
                              PlacementDay, Reason, SnapshotView, run)
from app.rules.zero_conv_placements import ZERO_CONV_PLACEMENTS as RULE
from app.sync.parse import placement_id

TO = date(2026, 9, 30)
PARTIAL = TO - timedelta(2)
DONE = TO - timedelta(4)  # завершённый день внутри окна оценки (24–30.09)
CID = 101
SOURCES = frozenset({"yandex_direct", DIRECT_CONVERSIONS, DIRECT_PLACEMENTS})


def cday(cid, day, cost, clicks, conv) -> CampaignDay:
    return CampaignDay(cid, day, Decimal(cost), clicks, None if conv is None else Decimal(conv))


def pday(cid, name, day, cost, clicks, conv) -> PlacementDay:
    return PlacementDay(cid, placement_id(name), day, Decimal(cost), clicks,
                        None if conv is None else Decimal(conv), name)


def view(campaign_days, placement_days, partial_from=PARTIAL, sources=SOURCES) -> SnapshotView:
    return SnapshotView(84721, 7, 3, TO - timedelta(36), TO, frozenset(sources), tuple(campaign_days),
                        placement_days=tuple(placement_days), partial_from=partial_from)


# CPA кампании ровно 1500 ₽: 30 000 ₽ / 20 конверсий
CAMPAIGN = [cday(CID, TO - timedelta(20), "30000.00", 1000, "20")]


def evaluate(placements, settings=AuditSettings(), campaign=CAMPAIGN, **kw):
    return run(RULE, view(campaign, placements, **kw), settings)


def ned(reason=Reason.VOLUME_INSUFFICIENT, cid=CID):
    """«Недостаточно данных» по кампании: площадки без конверсий есть, но вывода по ним сделать нельзя."""
    return (NotEnoughData("zero_conv_placements@1", reason, "campaign", cid),)


# --- Пороги на границах ---------------------------------------------------------------------------------

@pytest.mark.parametrize("cost, clicks, flagged", [
    ("1500.00", 20, True),    # ровно 1 × CPA и ровно 20 кликов — проходит
    ("1499.99", 200, False),  # на копейку меньше CPA
    ("9000.00", 19, False),   # кликов меньше порога
])
def test_thresholds_are_inclusive(cost, clicks, flagged):
    out = evaluate([pday(CID, "a.ru", DONE, cost, clicks, "0")])
    if not flagged:
        assert out == ned()  # ниже порога — не «проблема ушла», а «недостаточно данных»
        return
    (f,) = out
    assert f.lost.amount == Decimal(cost) and f.reference == Decimal("1500.00")


def test_thresholds_sum_days_inside_window_only():
    """Расход до окна оценки в порог не входит; конверсия до окна — входит (площадка уже конвертировала)."""
    before = TO - timedelta(10)
    assert evaluate([pday(CID, "a.ru", before, "5000.00", 100, "0"), pday(CID, "a.ru", DONE, "10.00", 1, "0")]) == ned()
    two_days = [pday(CID, "a.ru", DONE, "800.00", 10, "0"), pday(CID, "a.ru", DONE - timedelta(1), "700.00", 10, "0")]
    (f,) = evaluate(two_days)
    assert f.lost.amount == Decimal("1500.00")
    assert evaluate(two_days + [pday(CID, "a.ru", TO - timedelta(30), "1.00", 1, "1")]) == ()


def test_any_conversion_in_window_excludes_placement():
    assert evaluate([pday(CID, "a.ru", DONE, "5000.00", 100, "0.5")]) == ()


def test_masked_placement_is_never_proposed():
    assert evaluate([pday(CID, "***", DONE, "50000.00", 1000, "0")]) == ()


def test_campaign_without_network_spend_in_window_is_silent():
    assert evaluate([pday(CID, "a.ru", TO - timedelta(15), "5000.00", 100, "0")]) == ()
    assert evaluate([]) == ()


# --- Ориентир CPA ---------------------------------------------------------------------------------------

def test_target_cpa_is_reference_when_set():
    (f,) = evaluate([pday(CID, "a.ru", DONE, "1000.00", 30, "0")], AuditSettings(target_cpa=Decimal(1000)))
    assert (f.reference, f.reference_type, f.evidence_meta["reference_mode"]) == (Decimal(1000), "target", "target")
    assert f.evidence["reference_cpa"].source == "user_input" and f.lost.source.endswith("+user_input")
    # без цели тот же расход ниже CPA кампании (1500) — вывода нет
    assert evaluate([pday(CID, "a.ru", DONE, "1000.00", 30, "0")]) == ned()


@pytest.mark.parametrize("conversions, reason", [
    ("0", Reason.NO_CONVERSIONS),
    ("4", Reason.BASELINE_DATA_INSUFFICIENT),
])
def test_no_reliable_reference_is_not_enough_data(conversions, reason):
    out = evaluate([pday(CID, "a.ru", DONE, "9000.00", 100, "0")],
                   campaign=[cday(CID, TO - timedelta(20), "30000.00", 1000, conversions)])
    assert out == (NotEnoughData("zero_conv_placements@1", reason, "campaign", CID),)


def test_without_conversion_source_rule_is_not_computed():
    out = run(RULE, view(CAMPAIGN, [pday(CID, "a.ru", DONE, "9000.00", 100, None)], sources={"yandex_direct"}),
              AuditSettings())
    assert out == (NotEnoughData("zero_conv_placements@1", Reason.SOURCE_MISSING),)


def test_without_placements_report_rule_is_not_computed():
    """Отчёта площадок в снимке нет: площадок «нет» не потому, что их проверили, — правило не вычисляется."""
    out = run(RULE, view(CAMPAIGN, [], sources={"yandex_direct", DIRECT_CONVERSIONS}), AuditSettings())
    assert out == (NotEnoughData("zero_conv_placements@1", Reason.SOURCE_MISSING),)


def test_unknown_placement_conversions_are_source_missing():
    assert evaluate([pday(CID, "a.ru", DONE, "9000.00", 100, None)]) == ned(Reason.SOURCE_MISSING)
    # проходящая площадка всё равно в выводе, неизвестная — нет
    (f,) = evaluate([pday(CID, "a.ru", DONE, "9000.00", 100, None), pday(CID, "b.ru", DONE, "9000.00", 100, "0")])
    assert f.action["placement_ids"] == (placement_id("b.ru"),)


# --- Досчёт конверсий -----------------------------------------------------------------------------------

def test_placement_passing_only_with_partial_days_is_marked():
    (f,) = evaluate([pday(CID, "a.ru", DONE, "1000.00", 30, "0"), pday(CID, "a.ru", TO, "600.00", 10, "0")])
    assert f.evidence_meta["level_reason"] == "conversions_partial"
    assert f.evidence_meta[f"placement_{placement_id('a.ru')}_status"] == "partial"


def test_solid_placement_has_no_partial_reason():
    (f,) = evaluate([pday(CID, "a.ru", DONE, "1600.00", 30, "0"), pday(CID, "a.ru", TO, "600.00", 10, "0")])
    assert "level_reason" not in f.evidence_meta


def test_unknown_partial_boundary_is_treated_as_partial():
    (f,) = evaluate([pday(CID, "a.ru", DONE, "1600.00", 30, "0")], partial_from=None)
    assert f.evidence_meta["level_reason"] == "conversions_partial"


@pytest.mark.parametrize("cost, partial, quality", [
    ("4499.99", False, "low"),       # < 3 ожидаемых конверсий
    ("4500.00", False, "medium"),    # ровно 3
    ("15000.00", False, "high"),     # ровно 10
    ("15000.00", True, "medium"),    # high, но конверсии досчитываются → не выше review
])
def test_data_quality_by_expected_conversions(cost, partial, quality):
    days = [pday(CID, "a.ru", DONE, cost, 500, "0")]
    (f,) = evaluate(days, partial_from=None if partial else PARTIAL)
    assert f.current_data_quality == quality


# --- Вывод: агрегат по кампании, доказательства по площадкам -------------------------------------------

def test_one_finding_per_campaign_with_placements_in_evidence():
    placements = [pday(CID, "a.ru", DONE, "1600.00", 30, "0"), pday(CID, "b.ru", DONE, "3000.00", 50, "0"),
                  pday(202, "a.ru", DONE, "1600.00", 30, "0")]
    campaign = CAMPAIGN + [cday(202, TO - timedelta(20), "30000.00", 1000, "20")]
    f1, f2 = evaluate(placements, campaign=campaign)
    assert (f1.object_type, f1.object_id, f2.object_id) == ("campaign", CID, 202)
    a, b = placement_id("a.ru"), placement_id("b.ru")
    assert f1.action == {"type": "exclude_placements", "execution": "manual", "placement_ids": (b, a)}  # по расходу
    assert f1.evidence_meta["placement_ids"] == f"{b},{a}"
    assert (f1.evidence_meta[f"placement_{a}_name"], f1.evidence_meta[f"placement_{b}_name"]) == ("a.ru", "b.ru")
    # сумма по площадкам = exposure: audit/exposure.py объединяет по (кампания, площадка, период)
    per_placement = [x for k, x in f1.evidence.items() if k.startswith("placement_") and k.endswith("_cost")]
    assert sum(x.amount for x in per_placement) == f1.lost.amount == f1.evidence["cost"].amount == Decimal("4600.00")
    assert {(x.period.date_from, x.period.date_to) for x in per_placement} == {(TO - timedelta(6), TO)}
    assert f1.evidence["placements"].amount == 2 and f1.evidence["conversions"].amount == 0
    assert (f1.lost.calculation_type, f1.recoverable.calculation_type) == ("estimated", "unavailable")
    assert f1.lost.formula


def test_issue_key_is_campaign_level_and_stable_across_placement_sets():
    (f1,) = evaluate([pday(CID, "a.ru", DONE, "1600.00", 30, "0")])
    (f2,) = evaluate([pday(CID, "b.ru", DONE, "1600.00", 30, "0")])
    assert f1.issue_key == f2.issue_key and f1.issue_type == "zero_conv_placements"


def test_names_unknown_when_loaded_from_db():
    (f,) = evaluate([dataclasses.replace(pday(CID, "a.ru", DONE, "1600.00", 30, "0"), placement=None)])
    assert f.evidence_meta["placement_ids"] == str(placement_id("a.ru"))
    assert not any(k.endswith("_name") for k in f.evidence_meta)


def test_deterministic():
    days = [pday(CID, n, DONE, "1600.00", 30, "0") for n in ("a.ru", "b.ru", "c.ru")]
    assert evaluate(days) == evaluate(list(reversed(days)))


def test_every_fact_is_a_valid_value_in_python_and_sql(rw):
    (f,) = evaluate([pday(CID, "a.ru", DONE, "1600.00", 30, "0"), pday(CID, "b.ru", TO, "2000.00", 40, "0")])
    values = {k: to_value(x, 84721, PARTIAL, f.rule_version).model_dump(mode="json")
              for k, x in {**f.evidence, "lost": f.lost, "recoverable": f.recoverable}.items()}
    assert all(Value(**v) for v in values.values())
    assert rw.execute("SELECT evidence_is_valid(%s)", (Jsonb(values),)).fetchone()[0] is True
    assert json.loads(json.dumps(dict(f.action))) == {"type": "exclude_placements", "execution": "manual",
                                                      "placement_ids": list(f.action["placement_ids"])}


def test_exposure_basis_is_declared_placement_spend():
    """Основа exposure — расход перечисленных площадок кампании за окно (audit/exposure.py не угадывает её)."""
    (f,) = evaluate([pday(CID, "b.ru", DONE, "3000.00", 50, "0"), pday(CID, "a.ru", DONE, "1600.00", 30, "0")])
    ids = tuple(sorted((placement_id("a.ru"), placement_id("b.ru"))))
    assert f.exposure_basis == ExposureBasis("spend", "placement", ids)
    assert set(ids) == set(f.action["placement_ids"])


def test_recoverable_is_unavailable_not_a_copy_of_exposure():
    """Модели перераспределения бюджета после исключения площадок в v1.0 нет: «Можно сэкономить» — unavailable."""
    (f,) = evaluate([pday(CID, "a.ru", DONE, "1600.00", 30, "0")])
    assert (f.recoverable.amount, f.recoverable.calculation_type, f.recoverable.reason) == (
        None, "unavailable", "no_forecast")
    assert f.recoverable.unit == "rub" and f.recoverable.period == f.lost.period


# --- Объяснение (шаблон, без LLM) -----------------------------------------------------------------------

def test_template_uses_only_finding_numbers_and_names():
    (f,) = evaluate([pday(CID, "a.ru", DONE, "3000.00", 90, "0"), pday(CID, "f.ru", DONE, "1600.00", 60, "0")])
    text = explain(f, decide(f))
    assert "площадок РСЯ без конверсий: 2" in text and "4 600 ₽" in text and "150 кликов" in text
    assert "1 500 ₽" in text and "CPA кампании" in text and "a.ru, f.ru" in text
    assert "отклонение" not in text and "0%" not in text and "%" not in text
    assert "исключите" in text and "верхняя оценка" not in text  # review: исключить вручную; прогноза нет
    numbers = {n.strip() for n in re.findall(r"[0-9][0-9 ]*", text)}
    assert numbers <= {str(CID), "2", "4 600", "150", "1 500"}  # объект, число площадок, расход, клики, ориентир


def test_template_low_data_and_partial_and_unknown_names():
    (f,) = evaluate([dataclasses.replace(pday(CID, "a.ru", DONE, "1000.00", 30, "0"), placement=None),
                     pday(CID, "b.ru", DONE, "500.00", 15, "0"), pday(CID, "b.ru", TO, "600.00", 10, "0")],
                    AuditSettings(target_cpa=Decimal(1000)))
    d = decide(f)
    assert d.level == "inspect_only"
    text = explain(f, d)
    assert "целевой CPA 1 000 ₽" in text and "досчитываются" in text and "прежде чем исключать" in text
    assert "исключите лишние" not in text
