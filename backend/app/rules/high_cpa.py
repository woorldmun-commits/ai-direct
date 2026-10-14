"""CPA выше целевого или базового уровня (PRD §4, §4.1). Одно семейство проблемы, две версии правил:

high_cpa_target@1   — target_cpa задан → сравнение с target → можно предложить снизить ставку.
high_cpa_baseline@1 — target_cpa не задан → сравнение с baseline → только «проверить причину» + «укажите целевой CPA».

Общий evaluator, режим — параметр версии. issue_key у обеих одинаковый (family + объект): если клиент задал target,
проблема и рекомендация остаются теми же, меняется только вывод.

@2 (те же пороги): источник конверсий и CPA — yandex_direct из реестра метрик (Reports API Директа, а не Метрика);
в evidence_meta — цели и атрибуция снимка, без них (conversion_definition нет) правило не вычисляется. Конверсии дней
досчёта (date ≥ partial_from) — не финальные: если без них вывод не держится (по завершённым дням CPA не выше порога
срабатывания), достаточность данных не выше medium и level_reason = conversions_partial — как в zero_conv_*. Неизвестные
конверсии (None) за день окна — SOURCE_MISSING, а не ноль.

@3 — статистический порог вместо «CPA выше ориентира на 10%»: при 20 конверсиях в неделю кампания ровно на цели
получала «снизить ставку» в ~38% недель (шум Пуассона ±22%). Теперь вывод — только если и нижняя граница CPA выше
ориентира × trigger_margin: cost / upper90(conversions) > reference × 1,1, где upper90 — односторонняя 90% верхняя
граница среднего Пуассона (rules/poisson.py). Доля ложных выводов на кампании «ровно на цели» ≤ 5% при λ = 10…30
(tests/test_high_cpa_v3.py). Достаточность: high от 30 конверсий, medium от 10. target_cpa — на базе расхода (с НДС,
AuditSettings.target_cpa_gross; vat_basis в evidence_meta). lost = cost − ориентир × конверсии — без округлённого CPA."""

from datetime import date
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from dataclasses import replace

from app.rules.domain import (DIRECT_CONVERSIONS, FORMULA, AuditSettings, CampaignDay, Fact, Finding, NotEnoughData,
                              Output, Reason, Rule, SnapshotView, Window, frozen, issue_key, windows)
from app.rules.evidence import PARTIAL, definition_meta, definition_missing, labels, target_reference, user_input
from app.rules.poisson import Z90, upper

FAMILY = "high_cpa"
CPA_FORMULA = "period_total_spend / period_total_conversions"
CENT = Decimal("0.01")
ROUNDING = {"floor": ROUND_FLOOR}


def _sum(days: list[CampaignDay], window: Window) -> tuple[Decimal, Decimal]:
    inside = [d for d in days if d.date in window]
    return sum((d.cost for d in inside), Decimal(0)), sum((d.conversions for d in inside), Decimal(0))


def _unknown(days: list[CampaignDay], window: Window) -> bool:
    """Конверсии неизвестны хотя бы за один день окна: ноль конверсий не выводится из их отсутствия."""
    return any(d.conversions is None for d in days if d.date in window)


def _quality_v2(rule: Rule, snap: SnapshotView, days: list[CampaignDay], evaluation: Window, reference: Decimal,
                conv: Decimal) -> tuple[str, bool]:
    """@2: (достаточность данных, вывод опирается на дни досчёта). Конверсии дней досчёта ещё приходят, поэтому
    достаточность считается по конверсиям завершённых дней (те же пороги), а если вывод держится не на них (CPA по
    завершённым дням ниже порога срабатывания или конверсий там нет) — не выше medium."""
    done_cost, done_conv = _sum([d for d in days if snap.partial_from is not None and d.date < snap.partial_from],
                                evaluation)
    p = rule.params
    quality = _current_data_quality(done_conv, p)
    solid = _triggered(rule, done_cost, done_conv, reference)
    if not solid and quality == "high":
        quality = "medium"
    return quality, not solid or quality != _current_data_quality(conv, p)


def _triggered(rule: Rule, cost: Decimal, conv: Decimal, reference: Decimal) -> bool:
    """Срабатывает ли правило. @1–@2: точный CPA выше ориентира на trigger_delta_pct. @3: нижняя граница CPA
    (cost / верхняя граница конверсий) выше ориентира × trigger_margin — превышение не объясняется шумом Пуассона."""
    if conv <= 0:
        return False
    p = rule.params
    if rule.version < 3:
        return delta_pct(cost / conv, reference) >= p["trigger_delta_pct"]
    return cost / upper(conv, p["trigger_z"]) > reference * p["trigger_margin"]


def _lost(rule: Rule, cost: Decimal, conv: Decimal, cpa: Decimal, reference: Decimal) -> Decimal:
    """@3: cost − ориентир × конверсии (точно). @1–@2 — от округлённого CPA, как были записаны их выводы."""
    raw = cost - reference * conv if rule.version >= 3 else (cpa - reference) * conv
    return raw.quantize(CENT, ROUND_HALF_UP)


def _current_data_quality(conversions: Decimal, p) -> str:
    """Достаточность данных текущего периода; уровень действия по ней режет политика (audit/policy.py)."""
    if conversions >= p["current_high_conversions"]:
        return "high"
    if conversions >= p["current_medium_conversions"]:
        return "medium"
    return "low"


def _baseline_quality(conversions: Decimal, p) -> str | None:
    if conversions >= p["baseline_high_conversions"]:
        return "high"
    if conversions >= p["baseline_min_conversions"]:
        return "medium"
    return None


def delta_pct(actual: Decimal, reference: Decimal) -> Decimal:
    """Точное отклонение в Decimal. Пороги сравниваются с ним, а не с округлённым до 0,1 значением для показа:
    иначе 39,99% стало бы 40,0% и дало лишний шаг."""
    return (actual - reference) / reference * 100


def bid_change(delta: Decimal, p) -> int:
    """steps = floor(delta / step_excess_pct); изменение = −clamp(steps × bid_change_step_pct, min, max)."""
    steps = int((delta / p["step_excess_pct"]).to_integral_value(ROUNDING[p["rounding"]]))
    return -min(max(steps * p["bid_change_step_pct"], p["min_bid_change_pct"]), p["max_bid_change_pct"])


def _reference(rule: Rule, snap: SnapshotView, settings: AuditSettings, days, evaluation: Window,
               baseline: Window, account_history_from: date) -> tuple[Decimal, dict, dict] | Reason:
    """Ориентир сравнения: (значение, доказательства, meta) или причина, почему его нет."""
    if rule.params["mode"] == "target":
        if rule.version >= 3:
            return target_reference(settings, evaluation)
        return settings.target_cpa, {"target_cpa": Fact(settings.target_cpa, "rub", "user_input", evaluation)}, {}
    # «Новый аккаунт» (PRD §4.1) — по первому дню с данными во всём аккаунте, а не в кампании: дни без показов
    # Директ не отдаёт, и кампания на паузе в начале окна иначе выглядела бы новой.
    if snap.period_from > baseline.date_from or account_history_from > baseline.date_from:
        return Reason.BASELINE_HISTORY_INSUFFICIENT
    if _unknown(days, baseline):
        return Reason.SOURCE_MISSING
    base_cost, base_conv = _sum(days, baseline)
    quality = _baseline_quality(base_conv, rule.params)
    if quality is None:  # baseline_cpa = null, а не 0 и не бесконечность
        return Reason.BASELINE_DATA_INSUFFICIENT
    reference = (base_cost / base_conv).quantize(CENT, ROUND_HALF_UP)
    if reference <= 0:  # расход в окне ~0 при конверсиях: ориентира нет, а не «CPA 0 ₽» (и не деление на ноль)
        return Reason.BASELINE_DATA_INSUFFICIENT
    conv_label, cpa_label = labels(rule)
    evidence = {
        "baseline_cost": Fact(base_cost, "rub", "yandex_direct", baseline),
        "baseline_conversions": Fact(base_conv, "count", conv_label, baseline),
        "baseline_cpa": Fact(reference, "rub", cpa_label, baseline, "estimated", CPA_FORMULA),
    }
    return reference, evidence, {"baseline_data_quality": quality}


def _evaluate_campaign(rule: Rule, snap: SnapshotView, settings: AuditSettings,
                       campaign_id: int, days: list[CampaignDay], account_history_from: date) -> Output | None:
    p, mode = rule.params, rule.params["mode"]
    evaluation, baseline = windows(snap.period_to)

    if _unknown(days, evaluation):
        return NotEnoughData(rule.rule_version, Reason.SOURCE_MISSING, "campaign", campaign_id)
    cost, conv = _sum(days, evaluation)
    if conv == 0:  # CPA не существует; расход без конверсий ловит другое правило
        return NotEnoughData(rule.rule_version, Reason.NO_CONVERSIONS, "campaign", campaign_id)
    ref = _reference(rule, snap, settings, days, evaluation, baseline, account_history_from)
    if isinstance(ref, Reason):
        return NotEnoughData(rule.rule_version, ref, "campaign", campaign_id)
    reference, ref_evidence, meta = ref

    cpa = (cost / conv).quantize(CENT, ROUND_HALF_UP)  # для показа и доказательств
    delta = delta_pct(cost / conv, reference)           # пороги — по точному CPA, не по округлённому
    if not _triggered(rule, cost, conv, reference):
        return None

    conv_label, cpa_label = labels(rule)
    quality, partial = (_current_data_quality(conv, p), False) if rule.version < 2 else \
        _quality_v2(rule, snap, days, evaluation, reference, conv)
    evidence = {
        "cost": Fact(cost, "rub", "yandex_direct", evaluation),
        "conversions": Fact(conv, "count", conv_label, evaluation),
        "cpa": Fact(cpa, "rub", cpa_label, evaluation, "estimated", CPA_FORMULA),
        **ref_evidence,
    }
    source = user_input(cpa_label) if mode == "target" else cpa_label
    formula = f"cost - {mode}_cpa * conversions" if rule.version >= 3 else f"(cpa - {mode}_cpa) * conversions"
    lost = Fact(_lost(rule, cost, conv, cpa, reference), "rub", source, evaluation, "estimated", formula)
    if mode == "target":
        action = {"type": "decrease_bid", "change_pct": bid_change(delta, p)}
    else:
        action = {"type": "investigate_cpa_growth", "suggest": "set_target_cpa"}

    return Finding(
        rule_version=rule.rule_version, issue_type=rule.family, object_type="campaign", object_id=campaign_id,
        issue_key=issue_key(snap.workspace_id, snap.direct_account_id, rule.family, "campaign", campaign_id),
        reason_code=f"cpa_above_{mode}", metric="cpa", actual=cpa, reference=reference, reference_type=mode,
        delta_pct=delta.quantize(Decimal("0.1"), ROUND_HALF_UP), lost=lost,
        # «Проверить» (baseline) — обоснованной формулы прогноза нет: «Можно сэкономить» не копирует lost (ARCHITECTURE §4).
        recoverable=lost if mode == "target" else Fact.unavailable("rub", source, evaluation, reason="no_forecast"),
        current_data_quality=quality,
        evidence=frozen(evidence),
        evidence_meta=frozen({**meta, **definition_meta(rule, snap), **(PARTIAL if partial else {})}),
        action=frozen(action),
        exposure_basis=FORMULA,  # (cpa − ориентир) × конверсии: на единицы расхода не раскладывается
    )


def evaluate(rule: Rule, snap: SnapshotView, settings: AuditSettings) -> tuple[Output, ...]:
    if missing := definition_missing(rule, snap):
        return missing
    if not snap.campaign_days:
        return ()
    by_campaign: dict[int, list[CampaignDay]] = {}
    for day in snap.campaign_days:
        by_campaign.setdefault(day.campaign_id, []).append(day)
    history_from = min(d.date for d in snap.campaign_days)
    results = (_evaluate_campaign(rule, snap, settings, cid, days, history_from)
               for cid, days in sorted(by_campaign.items()))
    return tuple(r for r in results if r is not None)


_SOURCES = frozenset({"yandex_direct", DIRECT_CONVERSIONS})
# ponytail: v1-значения, в PRD чисел нет — уточнить на реальных данных. Любое изменение = новая версия правила.
_COMMON = {"trigger_delta_pct": 10, "current_high_conversions": 10, "current_medium_conversions": 3}

HIGH_CPA_TARGET = Rule(
    id="high_cpa_target", version=1, family=FAMILY, required_sources=_SOURCES, evaluate=evaluate,
    applies=lambda settings: settings.target_cpa is not None,
    params=frozen({**_COMMON, "mode": "target", "step_excess_pct": 20, "bid_change_step_pct": 5,
                   "rounding": "floor", "min_bid_change_pct": 5, "max_bid_change_pct": 25}),
)
HIGH_CPA_BASELINE = Rule(
    id="high_cpa_baseline", version=1, family=FAMILY, required_sources=_SOURCES, evaluate=evaluate,
    applies=lambda settings: settings.target_cpa is None,
    params=frozen({**_COMMON, "mode": "baseline",
                   "baseline_high_conversions": 20,  # PRD §4.1: ≥ 20 → high
                   "baseline_min_conversions": 10}),  # 10–19 → medium, < 10 → baseline не считается
)

# @2 — те же пороги, другие метки источника, доказательства и досчёт (см. docstring модуля); @1 остаются для старых выводов.
HIGH_CPA_TARGET_V2 = replace(HIGH_CPA_TARGET, version=2)
HIGH_CPA_BASELINE_V2 = replace(HIGH_CPA_BASELINE, version=2)

# @3 — статистический порог и НДС (см. docstring модуля). Пороги — предложение до проверки на живых кабинетах.
_V3 = {
    # Нижняя граница CPA выше ориентира на 10%: при 90% односторонней границе ложный вывод «ровно на цели» ≤ 5%.
    "trigger_margin": Decimal("1.1"), "trigger_z": Z90,
    # ≥ 30 конверсий → high (относительная ошибка CPA ≈ 1/√30 ≈ 18%), ≥ 10 → medium, меньше → low (inspect_only).
    "current_high_conversions": 30, "current_medium_conversions": 10,
}
HIGH_CPA_TARGET_V3 = replace(HIGH_CPA_TARGET, version=3, params=frozen(
    {k: v for k, v in {**HIGH_CPA_TARGET.params, **_V3}.items() if k != "trigger_delta_pct"}))
HIGH_CPA_BASELINE_V3 = replace(HIGH_CPA_BASELINE, version=3, params=frozen(
    {k: v for k, v in {**HIGH_CPA_BASELINE.params, **_V3}.items() if k != "trigger_delta_pct"}))
