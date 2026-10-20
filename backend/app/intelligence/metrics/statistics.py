"""Статистическая проверка долей (CR = конверсии / клики) — защита от выводов по маленькой выборке (§9.4 ТЗ).

Интервал Уилсона 95%: в отличие от «p ± 1,96·√(p(1−p)/n)» не вылезает за [0, 1] и честен при p = 0 и малых n.
Изменение доли считается достоверным, только если интервалы двух периодов не пересекаются — консервативно
(пропускает часть реальных изменений, но не выдаёт шум за сигнал). Неизвестные или невозможные данные — None, не 0.
Смена метода — новая версия METHOD."""

from decimal import Decimal

METHOD = "wilson_95@1"
Z = Decimal("1.96")


def wilson(successes: Decimal | None, trials: Decimal | None) -> tuple[Decimal, Decimal] | None:
    if successes is None or trials is None or trials <= 0 or not 0 <= successes <= trials:
        return None
    p, z2 = successes / trials, Z * Z
    centre = (p + z2 / (2 * trials)) / (1 + z2 / trials)
    half = Z * (p * (1 - p) / trials + z2 / (4 * trials * trials)).sqrt() / (1 + z2 / trials)
    return max(Decimal(0), centre - half), min(Decimal(1), centre + half)


def rate_changed(before_successes, before_trials, after_successes, after_trials) -> bool | None:
    """True — доли достоверно различаются; False — различие в пределах шума; None — данных нет."""
    a, b = wilson(before_successes, before_trials), wilson(after_successes, after_trials)
    if a is None or b is None:
        return None
    return a[1] < b[0] or b[1] < a[0]
