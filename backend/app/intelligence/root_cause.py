"""Причины изменения CPA кампании (§41–§44 ТЗ): детерминированно, без LLM.

CPA = CPC / CR. Изменение CPA меньше MATERIALITY от исходного — не изменение. Вклад факторов — LMDI
(metrics/contribution.py); главный фактор — тот, чья доля в ΔCPA ≥ DOMINANT, иначе mixed; вклады разных знаков — всегда
mixed (доля одного фактора тогда может превысить 100% и не означает, что он «главный»). Если в изменении участвует CR,
его изменение обязано быть статистически достоверным
(metrics/statistics.py, интервалы Уилсона) — иначе причина «не установлена» и нужно больше данных.
Причинность не выше ASSOCIATED: «рост CPA связан с падением CR», а не «вызван». Смену структуры трафика (устройства,
регионы, сети) без срезов проверить нельзя — это всегда в limitations, а не молчаливое «проверено»."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.intelligence.metrics.contribution import METHOD as SPLIT_METHOD
from app.intelligence.metrics.contribution import Contribution, Period, cpa_contribution
from app.intelligence.metrics.statistics import METHOD as STAT_METHOD
from app.intelligence.metrics.statistics import rate_changed

METHOD = f"root_cause@1({SPLIT_METHOD},{STAT_METHOD})"
DOMINANT = Decimal("0.6")
MATERIALITY = Decimal("0.05")  # |ΔCPA| / CPA до: меньше — шум, а не изменение
NEXT_CHECKS = {"cr": ("conversion_goals", "landing_page", "segments"),
               "cpc": ("strategy", "auction", "network_placements"),
               "mixed": ("conversion_goals", "strategy", "segments")}


class Status(str, Enum):
    ASSOCIATED = "associated"
    NOT_ESTABLISHED = "not_established"
    NO_MATERIAL_CHANGE = "no_material_change"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class Cause:
    status: Status
    driver: str | None                 # cr · cpc · mixed
    contribution: Contribution | None
    cr_change_significant: bool | None
    next_checks: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ("mix_shift_not_checked",)
    method: str = METHOD


def _driver(c: Contribution) -> str:
    if c.cpc * c.cr < 0:
        return "mixed"
    delta = c.cpa_after - c.cpa_before
    if c.cr / delta >= DOMINANT:
        return "cr"
    if c.cpc / delta >= DOMINANT:
        return "cpc"
    return "mixed"


def explain(before: Period, after: Period) -> Cause:
    c = cpa_contribution(before, after)
    if c is None:
        return Cause(Status.INSUFFICIENT_DATA, None, None, None)
    significant = rate_changed(before.conversions, before.clicks, after.conversions, after.clicks)
    if abs(c.cpa_after - c.cpa_before) < MATERIALITY * c.cpa_before:
        return Cause(Status.NO_MATERIAL_CHANGE, None, c, significant)
    driver = _driver(c)
    if driver != "cpc" and significant is not True:  # CR участвует, но его изменение в пределах шума
        return Cause(Status.NOT_ESTABLISHED, driver, c, significant, ("more_data",))
    return Cause(Status.ASSOCIATED, driver, c, significant, NEXT_CHECKS[driver])
