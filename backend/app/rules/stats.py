"""Точные тесты на счётных данных без scipy — общие для правил и методик замера (audit/ импортирует rules/)."""

import math


def binomial_upper_tail(k: int, n: int, q: float) -> float:
    """P(X ≥ k), X ~ Bin(n, q). Через lgamma: на тысячах конверсий биномиальные коэффициенты не переполняются."""
    if k <= 0:
        return 1.0
    if k > n or q <= 0:
        return 0.0
    if q >= 1:
        return 1.0
    lq, lr, ln = math.log(q), math.log1p(-q), math.lgamma(n + 1)
    return min(1.0, sum(math.exp(ln - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lq + (n - i) * lr)
                        for i in range(k, n + 1)))


def binomial_lower_tail(k: int, n: int, q: float) -> float:
    """P(X ≤ k), X ~ Bin(n, q)."""
    return max(0.0, 1.0 - binomial_upper_tail(k + 1, n, q))
