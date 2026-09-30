"""Методика замера эффекта выполненной рекомендации high_cpa — чистая функция, как правила (ARCHITECTURE.md §5).

observed effect (что произошло) и saved («Сэкономлено», что продукт вправе показать) — разные вещи.
saved = конверсии_после × (CPA_до − CPA_после): деньги, сэкономленные на фактически полученных конверсиях против
прежнего CPA. Падение CPA за счёт урезанного объёма рекламы в saved не превращается: при заметном падении конверсий
или росте CPA saved = NULL. Любое сомнение — NULL, а не оптимистичная оценка."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Literal, Mapping

from app.rules.domain import CampaignDay, Fact, Window, frozen

POLICY = "high_cpa_measure@1"
# Стартовые параметры методики, не статистические пороги. Любое изменение — новая версия (…_measure@2); старые
# замеры остаются на @1 и не пересчитываются.
PARAMS = frozen({
    "min_before_conversions": 3,     # меньше — CPA «до» слишком шумный, сравнивать не с чем
    # drop_pct = (conv_before − conv_after) / conv_before × 100; drop_pct > 20 → saved = NULL (ровно 20% — допустимо)
    "max_conversion_drop_pct": 20,
    "final_data_wait_days": 14,      # сколько ждать окончательных данных за окно «после»; дальше — insufficient
})
CENT = Decimal("0.01")
CPA_FORMULA = "period_total_spend / period_total_conversions"
SAVED_FORMULA = "conversions_after * (cpa_before - cpa_after)"
DM = "yandex_direct+yandex_metrika"


@dataclass(frozen=True)
class Measured:
    verdict: Literal["effect", "no_effect", "insufficient"]
    before: Mapping[str, Fact]
    after: Mapping[str, Fact]
    saved: Fact | None
    effect: Mapping[str, str]  # reason + наблюдаемые изменения, строками (jsonb)


def _period(days: list[CampaignDay], window: Window) -> tuple[Decimal, Decimal, dict[str, Fact]]:
    inside = [d for d in days if d.date in window]
    cost = sum((d.cost for d in inside), Decimal(0))
    conv = sum((d.conversions or Decimal(0) for d in inside), Decimal(0))
    facts = {"cost": Fact(cost, "rub", "yandex_direct", window), "conversions": Fact(conv, "count", "yandex_metrika", window)}
    if conv > 0:
        facts["cpa"] = Fact((cost / conv).quantize(CENT, ROUND_HALF_UP), "rub", DM, window, "estimated", CPA_FORMULA)
    return cost, conv, facts


def _pct(new: Decimal, old: Decimal) -> str:
    return str(((new - old) / old * 100).quantize(Decimal("0.1"), ROUND_HALF_UP))


def measure_cpa(days: Iterable[CampaignDay], before: Window, after: Window, params=PARAMS) -> Measured:
    days = list(days)
    b_cost, b_conv, b_facts = _period(days, before)
    a_cost, a_conv, a_facts = _period(days, after)

    def result(verdict, reason, saved=None, **observed):
        return Measured(verdict, frozen(b_facts), frozen(a_facts), saved, frozen({"reason": reason, **observed}))

    if b_conv < params["min_before_conversions"]:
        return result("insufficient", "before_conversions_below_minimum")
    if a_cost == 0 and a_conv == 0:
        return result("insufficient", "no_activity_after")  # кампанию остановили — эффект ставки не измерить
    if a_conv == 0:
        return result("no_effect", "no_conversions_after")
    cpa_b, cpa_a = b_cost / b_conv, a_cost / a_conv
    observed = {"cpa_change_pct": _pct(cpa_a, cpa_b), "conversions_change_pct": _pct(a_conv, b_conv)}
    if cpa_a >= cpa_b:
        return result("no_effect", "cpa_not_lower", **observed)
    if a_conv < b_conv * (1 - Decimal(params["max_conversion_drop_pct"]) / 100):
        return result("no_effect", "conversions_dropped", **observed)
    saved = Fact((a_conv * (cpa_b - cpa_a)).quantize(CENT, ROUND_HALF_UP), "rub", DM, after, "estimated", SAVED_FORMULA)
    return result("effect", "cpa_lower_at_same_volume", saved, **observed)
