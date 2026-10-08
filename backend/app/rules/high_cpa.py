"""CPA выше целевого или базового уровня (PRD §4, §4.1). Одно семейство проблемы, две версии правил:

high_cpa_target@1   — target_cpa задан → сравнение с target → можно предложить снизить ставку.
high_cpa_baseline@1 — target_cpa не задан → сравнение с baseline → только «проверить причину» + «укажите целевой CPA».

Общий evaluator, режим — параметр версии. issue_key у обеих одинаковый (family + объект): если клиент задал target,
проблема и рекомендация остаются теми же, меняется только вывод.

@2 (те же пороги): источник конверсий и CPA — yandex_direct из реестра метрик (Reports API Директа, а не Метрика);
в evidence_meta — цели и атрибуция снимка, без них (conversion_definition нет) правило не вычисляется. Конверсии дней
досчёта (date ≥ partial_from) — не финальные: если без них вывод не держится (по завершённым дням CPA не выше порога
срабатывания), достаточность данных не выше medium и level_reason = conversions_partial — как в zero_conv_*. Неизвестные
конверсии (None) за день окна — SOURCE_MISSING, а не ноль."""

from datetime import date
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from dataclasses import replace

from app.rules.domain import (DIRECT_CONVERSIONS, FORMULA, AuditSettings, CampaignDay, Fact, Finding, NotEnoughData,
                              Output, Reason, Rule, SnapshotView, Window, frozen, issue_key, windows)
from app.rules.evidence import PARTIAL, definition_meta, definition_missing, labels, user_input

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


def _solid(rule: Rule, snap: SnapshotView, days: list[CampaignDay], evaluation: Window, reference: Decimal) -> bool:
    """@2: держится ли вывод на завершённых днях окна. Конверсии дней досчёта ещё приходят — CPA по ним завышен."""
    if rule.version < 2:
        return True
    cost, conv = _sum([d for d in days if snap.partial_from is not None and d.date < snap.partial_from], evaluation)
    return conv > 0 and delta_pct(cost / conv, reference) >= rule.params["trigger_delta_pct"]


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
    if delta < p["trigger_delta_pct"]:
        return None

    conv_label, cpa_label = labels(rule)
    solid = _solid(rule, snap, days, evaluation, reference)
    quality = _current_data_quality(conv, p)
    evidence = {
        "cost": Fact(cost, "rub", "yandex_direct", evaluation),
        "conversions": Fact(conv, "count", conv_label, evaluation),
        "cpa": Fact(cpa, "rub", cpa_label, evaluation, "estimated", CPA_FORMULA),
        **ref_evidence,
    }
    source = user_input(cpa_label) if mode == "target" else cpa_label
    lost = Fact(((cpa - reference) * conv).quantize(CENT, ROUND_HALF_UP), "rub", source, evaluation,
                "estimated", f"(cpa - {mode}_cpa) * conversions")
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
        current_data_quality="medium" if not solid and quality == "high" else quality,
        evidence=frozen(evidence),
        evidence_meta=frozen({**meta, **definition_meta(rule, snap), **({} if solid else PARTIAL)}),
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
