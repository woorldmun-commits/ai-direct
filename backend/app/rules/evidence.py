"""Метки источников и определение конверсии в доказательствах правил. Версия @1 держит прежние метки (старые выводы
не пересчитываются), @2 берёт источник конверсий и CPA из реестра метрик и кладёт в evidence_meta цели и атрибуцию.
Чистый модуль, как остальной rules/."""

from decimal import Decimal

from app.intelligence.metrics.definitions import DEFINITIONS, VERSION, source_of_truth
from app.rules.domain import VAT_RATE, AuditSettings, Fact, NotEnoughData, Reason, Rule, SnapshotView, Window

LEGACY_LABELS = ("yandex_metrika", "yandex_direct+yandex_metrika")  # (конверсии, CPA) у @1
PARTIAL_REASON = "conversions_partial"  # evidence_meta.level_reason и причина понижения в safety_policy@2
PARTIAL = {"level_reason": PARTIAL_REASON}
# Семейства, у которых @1 — прежние метки (до реестра метрик). Новые правила с первой версии — на реестре.
LEGACY_FAMILIES = frozenset({"high_cpa", "zero_conv_campaign", "zero_conv_placements"})


def _legacy(rule: Rule) -> bool:
    return rule.version < 2 and rule.family in LEGACY_FAMILIES


def labels(rule: Rule) -> tuple[str, str]:
    """(источник конверсий, источник CPA)."""
    return LEGACY_LABELS if _legacy(rule) else (source_of_truth("conversions"), source_of_truth("cpa"))


def user_input(label: str) -> str:
    return label + "+user_input"


def definition_meta(rule: Rule, snap: SnapshotView) -> dict[str, str]:
    """Цели и атрибуция, по которым посчитаны конверсии вывода (@2). Факта о конверсиях без них не бывает."""
    d = snap.conversion_definition
    if _legacy(rule) or d is None:
        return {}
    conversions = DEFINITIONS["conversions"]  # CPA и CR наследуют оба источника от конверсий
    return {"goal_ids": ",".join(map(str, d.goal_ids)), "attribution_model": d.attribution,
            "retrieval_source": conversions.source_of_truth,      # откуда число: отчёт Директа
            "measurement_source": conversions.measurement_source,  # кто измерил конверсии: Метрика
            "metric_definitions": VERSION}


def definition_missing(rule: Rule, snap: SnapshotView) -> tuple[NotEnoughData, ...] | None:
    """@2 без определения конверсии в снимке не вычисляется: числа без целей и атрибуции сравнивать нечем."""
    if not _legacy(rule) and snap.conversion_definition is None:
        return (NotEnoughData(rule.rule_version, Reason.SOURCE_MISSING),)
    return None


VAT_FORMULA = "target_cpa * (1 + vat_rate)"


def target_reference(settings: AuditSettings, period: Window, key: str = "target_cpa") -> tuple[Decimal, dict, dict]:
    """Целевой CPA на базе расхода (с НДС) для правил @3: (ориентир, доказательства, meta). Введён без НДС — в
    доказательствах и исходное число (user_input), и пересчитанное с НДС (estimated); vat_basis — всегда."""
    gross = settings.target_cpa_gross()
    facts = {key: Fact(settings.target_cpa, "rub", "user_input", period)}
    if not settings.target_cpa_includes_vat:
        facts[f"{key}_with_vat"] = Fact(gross, "rub", "user_input", period, "estimated", VAT_FORMULA)
    return gross, facts, vat_meta(settings)


def vat_meta(settings: AuditSettings) -> dict[str, str]:
    """На какой базе НДС введён target_cpa (evidence_meta.vat_basis)."""
    if settings.target_cpa_includes_vat:
        return {"vat_basis": "target_includes_vat"}
    return {"vat_basis": "target_net_converted", "vat_rate": str(VAT_RATE)}
