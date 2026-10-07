"""Разложение CPA = CPC / CR: что подняло стоимость конверсии — цена клика или конверсия из клика. Окно оценки против
базового периода той же кампании (не против цели: у цели нет CPC и CR).

Считается только по дням с окончательными конверсиями (date < partial_from): у досчитываемых дней CR занижен, и
«упала конверсия» было бы артефактом. Нет таких дней, база < decomposition_min_baseline_conversions или CPA этих дней
не выше базового — разложения нет (пустые факты): высокий CPA целиком в досчитываемых днях объяснять нечем.

Причина называется, только если она не шум (пороги — параметры версии правила, УТВЕРЖДАЕТ ВЛАДЕЛЕЦ ПРОДУКТА):
  cpc — CPC вырос на ≥ cpc_growth_pct (кликов — десятки и сотни, средняя цена клика стабильна);
  cr  — CR упал значимо: P(X ≤ конверсии_окна) < cr_drop_max_p, X ~ Bin(конверсии_окна + конверсии_базы,
        клики_окна / (клики_окна + клики_базы)) — при неизменном CR конверсии делятся пропорционально кликам;
  cpc_and_cr — оба; unclear — ни один: числа показываются, причина — нет."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.rules.domain import CampaignDay, Fact, Window
from app.rules.stats import binomial_lower_tail

CENT = Decimal("0.01")
CPC_FORMULA = "period_total_spend / period_total_clicks"
CR_FORMULA = "period_total_conversions / period_total_clicks * 100"
DM = "yandex_direct+yandex_metrika"


def _totals(days: list[CampaignDay], window: Window) -> tuple[Decimal, int, Decimal]:
    inside = [d for d in days if d.date in window]
    return (sum((d.cost for d in inside), Decimal(0)), sum(d.clicks for d in inside),
            sum((d.conversions or Decimal(0) for d in inside), Decimal(0)))


def _facts(prefix: str, cost: Decimal, clicks: int, conv: Decimal, window: Window) -> dict[str, Fact]:
    return {f"{prefix}clicks": Fact(Decimal(clicks), "count", "yandex_direct", window),
            f"{prefix}cpc": Fact((cost / clicks).quantize(CENT, ROUND_HALF_UP), "rub", "yandex_direct", window,
                                 "estimated", CPC_FORMULA),
            f"{prefix}cr": Fact((conv / clicks * 100).quantize(CENT, ROUND_HALF_UP), "pct", DM, window,
                                "estimated", CR_FORMULA)}


def _count(conversions: Decimal) -> int:
    return int(conversions.to_integral_value(ROUND_HALF_UP))


def decompose(days: list[CampaignDay], evaluation: Window, baseline: Window, partial_from: date | None,
              p) -> tuple[dict[str, Fact], dict[str, str]]:
    """(факты, meta) или ({}, {}) — разложения нет."""
    if partial_from is None:
        return {}, {}
    solid = Window(evaluation.date_from, min(evaluation.date_to, partial_from - timedelta(1)))
    cost, clicks, conv = _totals(days, solid)
    b_cost, b_clicks, b_conv = _totals(days, baseline)
    if (solid.date_to < solid.date_from or clicks == 0 or b_clicks == 0 or b_cost <= 0
            or b_conv < p["decomposition_min_baseline_conversions"]
            or cost * b_conv <= b_cost * conv):  # CPA окончательных дней не выше базового (при conv = 0 — выше)
        return {}, {}
    cpc_up = cost * b_clicks * 100 >= b_cost * clicks * (100 + p["cpc_growth_pct"])
    p_drop = binomial_lower_tail(_count(conv), _count(conv + b_conv), clicks / (clicks + b_clicks))
    cr_down = p_drop < p["cr_drop_max_p"]
    driver = {(True, False): "cpc", (False, True): "cr", (True, True): "cpc_and_cr"}.get((cpc_up, cr_down), "unclear")
    facts = {**_facts("", cost, clicks, conv, solid), **_facts("baseline_", b_cost, b_clicks, b_conv, baseline)}
    return facts, {"cpa_driver": driver, "cr_drop_p": f"{p_drop:.3f}"}
