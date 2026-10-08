"""Метки источников и определение конверсии в доказательствах правил. Версия @1 держит прежние метки (старые выводы
не пересчитываются), @2 берёт источник конверсий и CPA из реестра метрик и кладёт в evidence_meta цели и атрибуцию.
Чистый модуль, как остальной rules/."""

from app.intelligence.metrics.definitions import VERSION, source_of_truth
from app.rules.domain import NotEnoughData, Reason, Rule, SnapshotView

LEGACY_LABELS = ("yandex_metrika", "yandex_direct+yandex_metrika")  # (конверсии, CPA) у @1
PARTIAL_REASON = "conversions_partial"  # evidence_meta.level_reason и причина понижения в safety_policy@2
PARTIAL = {"level_reason": PARTIAL_REASON}


def labels(rule: Rule) -> tuple[str, str]:
    """(источник конверсий, источник CPA)."""
    return LEGACY_LABELS if rule.version < 2 else (source_of_truth("conversions"), source_of_truth("cpa"))


def user_input(label: str) -> str:
    return label + "+user_input"


def definition_meta(rule: Rule, snap: SnapshotView) -> dict[str, str]:
    """Цели и атрибуция, по которым посчитаны конверсии вывода (@2). Факта о конверсиях без них не бывает."""
    d = snap.conversion_definition
    if rule.version < 2 or d is None:
        return {}
    return {"goal_ids": ",".join(map(str, d.goal_ids)), "attribution_model": d.attribution,
            "metric_definitions": VERSION}


def definition_missing(rule: Rule, snap: SnapshotView) -> tuple[NotEnoughData, ...] | None:
    """@2 без определения конверсии в снимке не вычисляется: числа без целей и атрибуции сравнивать нечем."""
    if rule.version >= 2 and snap.conversion_definition is None:
        return (NotEnoughData(rule.rule_version, Reason.SOURCE_MISSING),)
    return None
