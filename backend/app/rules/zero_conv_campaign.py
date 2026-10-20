"""Нулевые конверсии (STRATEGY.md §3, правило 1): кампания с расходом и 0 конверсий за окно оценки (7 дней) при
достаточном объёме данных. Одна версия — zero_conv_campaign@1; issue_key = семейство + кампания.

«Достаточный объём» — оба условия сразу (≥ — ровно на пороге правило срабатывает):
  расход ≥ spend_threshold   и   клики ≥ min_clicks.
spend_threshold = max(cpa_multiple × CPA-ориентир, min_cost_rub). CPA-ориентир — первый доступный из:
  1) target_cpa из настроек (reference_type = target);
  2) CPA самой кампании за baseline (30 дней до окна, ≥ baseline_min_conversions конверсий) — reference_type = baseline;
  3) CPA всего аккаунта за baseline (то же условие) — reference_type = baseline, reference_source = account_baseline;
  4) ориентира нет → абсолютный минимум absolute_min_cost_rub (reference_type = absolute).

Обоснование порогов v1 (ПОРОГИ УТВЕРЖДАЕТ ВЛАДЕЛЕЦ ПРОДУКТА; любое изменение — @2):
- cpa_multiple = 3. Если кампания работает «как обычно» (CPA ≈ ориентиру), за расход 3 × CPA ожидается λ = 3
  конверсии; по Пуассону P(0 | норма) = e⁻³ ≈ 5%. Меньше — слишком часто ложная тревога на обычном шуме.
- high_cpa_multiple = 5 → P(0 | норма) = e⁻⁵ ≈ 0,7%: от этого объёма current_data_quality = high.
- min_clicks = 50. Клики — число попыток: при CR 5% P(0 из 50) = 0,95⁵⁰ ≈ 8%, при CR 3% ≈ 22%; защищает от
  срабатывания на нескольких дорогих кликах. high_clicks = 100 → 0,95¹⁰⁰ ≈ 0,6%.
- min_cost_rub = 1 000 ₽ — нижняя граница порога при очень дешёвом CPA: меньшие суммы не стоят внимания владельца.
- absolute_min_cost_rub = 5 000 ₽ за 7 дней — когда CPA неизвестен (пример из ARCHITECTURE.md §4: «> 5 000 ₽ без
  конверсий»). Уверенность в этом режиме не выше medium: ожидаемое число конверсий неизвестно.
- baseline_min_conversions = 10 — как в high_cpa_baseline@1 (PRD §4.1): меньше — CPA ориентира не считается.

Действие — только «проверить» (investigate_zero_conversions, уровень inspect_only по safety_policy): правило не
знает стратегию кампании (в мире автостратегий ставку вручную не меняют), поэтому рычаги — проверка учёта целей и
конверсий, стратегии / цели CPA, поисковых запросов и минус-фраз. Ставку и бюджет правило не предлагает никогда.

Досчёт конверсий (partial): дни date ≥ partial_from — не настоящие нули, конверсии за них ещё приходят. Если порог
объёма достигается только с учётом этих дней (или partial_from неизвестен) — вывод остаётся, но достаточность данных
не выше medium и evidence_meta.level_reason = conversions_partial (lost за окно с такими днями — data_status partial).

Недостаточно данных: расход > 0 и 0 конверсий, но объём ниже порога → NotEnoughData(VOLUME_INSUFFICIENT) — открытая
проблема не «исчезает» от того, что расход упал ниже порога. Конверсии неизвестны (None) хотя бы за один день окна →
NotEnoughData(SOURCE_MISSING): ноль конверсий не выводится из их отсутствия. Расход 0 или есть конверсии → ничего.

lost (exposure) = весь расход кампании за окно оценки (estimated, формула ниже; основа exposure — вся кампания).
recoverable = unavailable: действие — «проверить», обоснованной формулы прогноза эффекта нет (ARCHITECTURE.md §4),
поэтому «Можно сэкономить» не копирует lost и не завышается.

@2 (те же пороги): источник конверсий и CPA — yandex_direct из реестра метрик (а не Метрика); в evidence_meta — цели и
атрибуция снимка, без определения конверсии (conversion_definition) правило не вычисляется (SOURCE_MISSING)."""

from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal

from app.rules.domain import (DIRECT_CONVERSIONS, SPEND_CAMPAIGN, AuditSettings, CampaignDay, Fact, Finding,
                              NotEnoughData, Output, Reason, Rule, SnapshotView, Window, frozen, issue_key, windows)
from app.rules.evidence import PARTIAL, definition_meta, definition_missing, labels

FAMILY = "zero_conv_campaign"
CPA_FORMULA = "period_total_spend / period_total_conversions"
THRESHOLD_FORMULA = "max(cpa_multiple * reference_cpa, min_cost_rub)"
LOST_FORMULA = "evaluation_window_spend where evaluation_window_conversions = 0"
CHECKS = ("conversion_goals", "strategy", "search_queries_negative_keywords")
CENT = Decimal("0.01")


def _totals(days: list[CampaignDay], window: Window) -> tuple[Decimal, int, Decimal]:
    inside = [d for d in days if d.date in window]
    return (sum((d.cost for d in inside), Decimal(0)), sum(d.clicks for d in inside),
            sum((d.conversions or Decimal(0) for d in inside), Decimal(0)))


def _baseline_cpa(days: list[CampaignDay], baseline: Window, prefix: str, p,
                  sources: tuple[str, str]) -> tuple[Decimal, dict] | None:
    if any(d.conversions is None for d in days if d.date in baseline):
        return None  # конверсии неизвестны: ориентира нет, а не «CPA по нулю конверсий»
    cost, _, conv = _totals(days, baseline)
    if conv < p["baseline_min_conversions"]:
        return None
    cpa = (cost / conv).quantize(CENT, ROUND_HALF_UP)
    if cpa <= 0:  # конверсии без расхода: ориентира нет, а не «CPA 0 ₽»
        return None
    return cpa, {f"{prefix}_cost": Fact(cost, "rub", "yandex_direct", baseline),
                 f"{prefix}_conversions": Fact(conv, "count", sources[0], baseline),
                 f"{prefix}_cpa": Fact(cpa, "rub", sources[1], baseline, "estimated", CPA_FORMULA)}


def _reference(rule: Rule, snap: SnapshotView, settings: AuditSettings, days: list[CampaignDay],
               evaluation: Window) -> tuple[str, str, Decimal | None, dict]:
    """(reference_type, reference_source, CPA-ориентир или None, доказательства ориентира)."""
    p = rule.params
    if settings.target_cpa is not None:
        return "target", "target_cpa", settings.target_cpa, {
            "target_cpa": Fact(settings.target_cpa, "rub", "user_input", evaluation)}
    _, baseline = windows(snap.period_to)
    history_from = min(d.date for d in snap.campaign_days)
    if snap.period_from <= baseline.date_from and history_from <= baseline.date_from:  # как в high_cpa (PRD §4.1)
        if found := _baseline_cpa(days, baseline, "baseline", p, labels(rule)):
            return "baseline", "campaign_baseline", *found
        if found := _baseline_cpa(list(snap.campaign_days), baseline, "account_baseline", p, labels(rule)):
            return "baseline", "account_baseline", *found
    return "absolute", "absolute_minimum", None, {}


def _evaluate_campaign(rule: Rule, snap: SnapshotView, settings: AuditSettings, campaign_id: int,
                       days: list[CampaignDay]) -> Output | None:
    p = rule.params
    evaluation, _ = windows(snap.period_to)
    cost, clicks, conv = _totals(days, evaluation)
    if cost <= 0 or conv > 0:
        return None  # нет расхода или конверсии есть — не эта проблема
    if any(d.conversions is None for d in days if d.date in evaluation):
        return NotEnoughData(rule.rule_version, Reason.SOURCE_MISSING, "campaign", campaign_id)

    ref_type, ref_source, ref_cpa, ref_evidence = _reference(rule, snap, settings, days, evaluation)
    if ref_cpa is None:
        threshold = Decimal(p["absolute_min_cost_rub"])
    else:
        threshold = max((p["cpa_multiple"] * ref_cpa).quantize(CENT, ROUND_HALF_UP), Decimal(p["min_cost_rub"]))
    if cost < threshold or clicks < p["min_clicks"]:
        return NotEnoughData(rule.rule_version, Reason.VOLUME_INSUFFICIENT, "campaign", campaign_id)

    complete = [d for d in days if d.date in evaluation and snap.partial_from is not None and d.date < snap.partial_from]
    solid = (sum((d.cost for d in complete), Decimal(0)) >= threshold
             and sum(d.clicks for d in complete) >= p["min_clicks"])
    high = (solid and ref_cpa is not None and cost >= p["high_cpa_multiple"] * ref_cpa and clicks >= p["high_clicks"])
    conv_label, cpa_label = labels(rule)
    evidence = {
        "cost": Fact(cost, "rub", "yandex_direct", evaluation),
        "clicks": Fact(Decimal(clicks), "count", "yandex_direct", evaluation),
        "conversions": Fact(conv, "count", conv_label, evaluation),
        **ref_evidence,
    }
    if ref_cpa is not None:
        source = "user_input" if ref_type == "target" else cpa_label
        evidence["spend_threshold"] = Fact(threshold, "rub", source, evaluation, "estimated", THRESHOLD_FORMULA)
    lost = Fact(cost.quantize(CENT, ROUND_HALF_UP), "rub", cpa_label, evaluation, "estimated", LOST_FORMULA)
    action = {"type": "investigate_zero_conversions", "check": CHECKS}
    if ref_type != "target":
        action["suggest"] = "set_target_cpa"

    return Finding(
        rule_version=rule.rule_version, issue_type=rule.family, object_type="campaign", object_id=campaign_id,
        issue_key=issue_key(snap.workspace_id, snap.direct_account_id, rule.family, "campaign", campaign_id),
        reason_code="zero_conversions", metric="cost", actual=cost, reference=threshold, reference_type=ref_type,
        delta_pct=((cost - threshold) / threshold * 100).quantize(Decimal("0.1"), ROUND_HALF_UP),
        lost=lost, recoverable=Fact.unavailable("rub", cpa_label, evaluation, reason="no_forecast"),
        current_data_quality="high" if high else "medium",
        evidence=frozen(evidence), action=frozen(action),
        evidence_meta=frozen({"reference_source": ref_source, **definition_meta(rule, snap),
                              **({} if solid else PARTIAL)}),
        exposure_basis=SPEND_CAMPAIGN,
    )


def evaluate(rule: Rule, snap: SnapshotView, settings: AuditSettings) -> tuple[Output, ...]:
    if missing := definition_missing(rule, snap):
        return missing
    by_campaign: dict[int, list[CampaignDay]] = {}
    for day in snap.campaign_days:
        by_campaign.setdefault(day.campaign_id, []).append(day)
    results = (_evaluate_campaign(rule, snap, settings, cid, days) for cid, days in sorted(by_campaign.items()))
    return tuple(r for r in results if r is not None)


ZERO_CONV_CAMPAIGN = Rule(
    id="zero_conv_campaign", version=1, family=FAMILY, required_sources=frozenset({"yandex_direct", DIRECT_CONVERSIONS}),
    evaluate=evaluate,
    # v1-значения; обоснование — в docstring модуля. Утверждены владельцем 2026-10-03 (PRODUCT_SPEC §9.1); изменение = @2.
    params=frozen({"cpa_multiple": 3, "high_cpa_multiple": 5, "min_clicks": 50, "high_clicks": 100,
                   "min_cost_rub": 1000, "absolute_min_cost_rub": 5000, "baseline_min_conversions": 10}),
)

# @2 — те же пороги, другие метки источника и доказательства; @1 остаётся для старых выводов.
ZERO_CONV_CAMPAIGN_V2 = replace(ZERO_CONV_CAMPAIGN, version=2)
