"""Вклад CPC и CR в изменение CPA (§43, §82 ТЗ). CPA = CPC / CR, разложение — LMDI (log-mean Divisia):

    L = (CPA₁ − CPA₀) / (ln CPA₁ − ln CPA₀)        (L = CPA₀, если CPA не изменился)
    вклад CPC = L · ln(CPC₁ / CPC₀),   вклад CR = −L · ln(CR₁ / CR₀)

Разложение точное (вклады в сумме = ΔCPA) и не зависит от порядка факторов — в отличие от последовательной
подстановки, где «кто первый, тот и больше». Вклад CR после округления = ΔCPA − вклад CPC: сумма сходится до копейки.
Нет кликов или конверсий в любом периоде (или они неизвестны) — None: разложение не определено, ноль не подставляем.
Смена метода — новая версия METHOD."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

METHOD = "cpa_contribution_lmdi@1"
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Period:
    cost: Decimal
    clicks: Decimal | None
    conversions: Decimal | None


@dataclass(frozen=True)
class Contribution:
    method: str
    cpa_before: Decimal
    cpa_after: Decimal
    cpc: Decimal   # ₽ изменения CPA за счёт цены клика
    cr: Decimal    # ₽ изменения CPA за счёт конверсии кликов


def _defined(p: Period) -> bool:
    return bool(p.clicks) and bool(p.conversions) and p.cost > 0


def cpa_contribution(before: Period, after: Period) -> Contribution | None:
    if not (_defined(before) and _defined(after)):
        return None
    cpa0, cpa1 = before.cost / before.conversions, after.cost / after.conversions
    cpc0, cpc1 = before.cost / before.clicks, after.cost / after.clicks
    weight = cpa0 if cpa0 == cpa1 else (cpa1 - cpa0) / (cpa1.ln() - cpa0.ln())
    cpc = (weight * (cpc1 / cpc0).ln()).quantize(CENT, ROUND_HALF_UP)
    before_r, after_r = cpa0.quantize(CENT, ROUND_HALF_UP), cpa1.quantize(CENT, ROUND_HALF_UP)
    return Contribution(METHOD, before_r, after_r, cpc, after_r - before_r - cpc)
