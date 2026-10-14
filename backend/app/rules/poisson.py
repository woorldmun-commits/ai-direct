"""Односторонние доверительные границы для среднего Пуассона (число конверсий за окно). Чистые функции на Decimal.

Аппроксимация Уилсона — Хилферти к точной границе Гарвуда (через χ²): ошибка < 1% уже при n ≥ 1, точнее нормальной
аппроксимации на малых числах конверсий, где именно и живёт шум. z — квантиль нормального: 1,2816 — 90%, 1,6449 — 95%."""

from decimal import Decimal

Z90 = Decimal("1.2816")
Z95 = Decimal("1.6449")
_ONE, _NINE, _THREE = Decimal(1), Decimal(9), Decimal(3)


def upper(n: Decimal, z: Decimal = Z90) -> Decimal:
    """Верхняя граница λ при наблюдённых n: P(X ≤ n | λ = upper) ≈ 1 − уровень."""
    m = Decimal(n) + 1
    return m * (_ONE - _ONE / (_NINE * m) + z / (_THREE * m.sqrt())) ** 3


def lower(n: Decimal, z: Decimal = Z90) -> Decimal:
    """Нижняя граница λ при наблюдённых n (0 при n = 0)."""
    n = Decimal(n)
    if n <= 0:
        return Decimal(0)
    return n * max(Decimal(0), _ONE - _ONE / (_NINE * n) - z / (_THREE * n.sqrt())) ** 3
