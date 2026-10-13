"""Недоиспользование бюджета при хорошем CPA. budget_underuse@1, за флагом audit_rules_candidates.

Кампания за окно оценки (7 дней) потратила не больше max_utilization_pct своего ограничения (недельный лимит
автостратегии, иначе дневной бюджет × 7), а её CPA за окно не выше good_cpa_share × ориентир (target_cpa, иначе CPA
кампании за базу 30 дней при ≥ baseline_min_conversions конверсиях) при ≥ min_conversions конверсиях в окне.
Это возможность, а не потери: lost и recoverable — unavailable (no_forecast), в итог «Расход с признаками
неэффективности» не входит. Действие — только «проверить», что сдерживает расход (стратегия, цель CPA, ставки, охват);
бюджет и ставки правило не предлагает (бюджет и так не израсходован). Тип действия — investigate_cpa_growth с
проверкой strategy (форма «проверить» и уровень inspect_only уже есть в контракте и safety_policy).

Данные: бюджеты кампаний (Campaigns.get) — возможность direct_budgets. Синхронизация их пока не читает: правило
не вычисляется (SOURCE_MISSING). Бюджет известен на момент снимка; если его меняли внутри окна, использование
считается от текущего — ограничение версии, проверить на живых кабинетах.
Досчёт: CPA считается по всем 7 дням — конверсии дней досчёта только прибавятся и CPA снизят, то есть
«хороший CPA» по неполным дням — консервативная оценка; понижать достаточность не нужно.

Недостаточно данных: использование низкое, но конверсий в окне < min_conversions → VOLUME_INSUFFICIENT; ориентира
нет → BASELINE_DATA_INSUFFICIENT; конверсии неизвестны → SOURCE_MISSING."""

from decimal import ROUND_HALF_UP, Decimal

from app.rules.domain import (DIRECT_BUDGETS, DIRECT_CONVERSIONS, EVALUATION_DAYS, FORMULA, AuditSettings,
                              CampaignBudget, CampaignDay, Fact, Finding, NotEnoughData, Output, Reason, Rule,
                              SnapshotView, Window, frozen, issue_key, windows)
from app.rules.evidence import definition_meta, definition_missing, labels

FAMILY = "budget_underuse"
CENT = Decimal("0.01")
CPA_FORMULA = "period_total_spend / period_total_conversions"
UTILIZATION_FORMULA = f"cost / (weekly_budget or daily_budget * {EVALUATION_DAYS}) * 100"
CHECKS = ("strategy",)


def _sum(days: list[CampaignDay], window: Window) -> tuple[Decimal, Decimal]:
    inside = [d for d in days if d.date in window]
    return sum((d.cost for d in inside), Decimal(0)), sum((d.conversions or Decimal(0) for d in inside), Decimal(0))


def _limit(b: CampaignBudget) -> Decimal | None:
    if b.weekly_budget is not None:
        return b.weekly_budget
    return None if b.daily_budget is None else b.daily_budget * EVALUATION_DAYS


def _reference(rule: Rule, settings: AuditSettings, days, evaluation: Window, baseline: Window):
    """(ориентир CPA, доказательства) или None."""
    if settings.target_cpa is not None:
        return settings.target_cpa, {"target_cpa": Fact(settings.target_cpa, "rub", "user_input", evaluation)}
    cost, conv = _sum(days, baseline)
    if conv < rule.params["baseline_min_conversions"] or cost <= 0:
        return None
    cpa = (cost / conv).quantize(CENT, ROUND_HALF_UP)
    return cpa, {"baseline_cpa": Fact(cpa, "rub", labels(rule)[1], baseline, "estimated", CPA_FORMULA)}


def _evaluate_campaign(rule: Rule, snap: SnapshotView, settings: AuditSettings, b: CampaignBudget,
                       days: list[CampaignDay]) -> Output | None:
    p, cid = rule.params, b.campaign_id
    evaluation, baseline = windows(snap.period_to)
    limit = _limit(b)
    if limit is None or limit <= 0:
        return None  # ограничения нет — недоиспользовать нечего
    cost, conv = _sum(days, evaluation)
    utilization = cost / limit * 100
    if utilization > p["max_utilization_pct"]:
        return None
    if any(d.conversions is None for d in days if d.date in evaluation or d.date in baseline):
        return NotEnoughData(rule.rule_version, Reason.SOURCE_MISSING, "campaign", cid)
    if conv < p["min_conversions"]:
        return NotEnoughData(rule.rule_version, Reason.VOLUME_INSUFFICIENT, "campaign", cid)
    ref = _reference(rule, settings, days, evaluation, baseline)
    if ref is None:
        return NotEnoughData(rule.rule_version, Reason.BASELINE_DATA_INSUFFICIENT, "campaign", cid)
    reference, ref_evidence = ref
    cpa = (cost / conv).quantize(CENT, ROUND_HALF_UP)
    if cost / conv > reference * p["good_cpa_share"]:
        return None  # CPA не «хороший»: наращивать расход не за чем
    conv_label, cpa_label = labels(rule)
    evidence = {"cost": Fact(cost, "rub", "yandex_direct", evaluation),
                "budget_limit": Fact(limit, "rub", "yandex_direct", evaluation),
                "utilization_pct": Fact(utilization.quantize(Decimal("0.1"), ROUND_HALF_UP), "pct", "yandex_direct",
                                        evaluation, "estimated", UTILIZATION_FORMULA),
                "conversions": Fact(conv, "count", conv_label, evaluation),
                "cpa": Fact(cpa, "rub", cpa_label, evaluation, "estimated", CPA_FORMULA), **ref_evidence}
    threshold = Decimal(p["max_utilization_pct"])
    none = Fact.unavailable("rub", cpa_label, evaluation, reason="no_forecast")  # возможность, а не потери
    return Finding(
        rule_version=rule.rule_version, issue_type=rule.family, object_type="campaign", object_id=cid,
        issue_key=issue_key(snap.workspace_id, snap.direct_account_id, rule.family, "campaign", cid),
        reason_code="budget_underused_good_cpa", metric="budget_utilization_pct",
        actual=utilization.quantize(Decimal("0.1"), ROUND_HALF_UP), reference=threshold, reference_type="absolute",
        delta_pct=((utilization - threshold) / threshold * 100).quantize(Decimal("0.1"), ROUND_HALF_UP),
        lost=none, recoverable=none,
        current_data_quality="medium" if conv >= p["medium_conversions"] else "low",
        evidence=frozen(evidence),
        evidence_meta=frozen({"reference_mode": "target" if settings.target_cpa is not None else "baseline",
                              "budget_kind": "weekly" if b.weekly_budget is not None else "daily",
                              **definition_meta(rule, snap)}),
        action=frozen({"type": "investigate_cpa_growth", "check": CHECKS}), exposure_basis=FORMULA)


def evaluate(rule: Rule, snap: SnapshotView, settings: AuditSettings) -> tuple[Output, ...]:
    if missing := definition_missing(rule, snap):
        return missing
    by_campaign: dict[int, list[CampaignDay]] = {}
    for day in snap.campaign_days:
        by_campaign.setdefault(day.campaign_id, []).append(day)
    results = (_evaluate_campaign(rule, snap, settings, b, by_campaign.get(b.campaign_id, []))
               for b in sorted(snap.budgets, key=lambda b: b.campaign_id))
    return tuple(r for r in results if r is not None)


# Пороги @1 — предложение до проверки на живых кабинетах (утверждает владелец; изменение = @2).
BUDGET_UNDERUSE = Rule(
    id="budget_underuse", version=1, family=FAMILY,
    required_sources=frozenset({"yandex_direct", DIRECT_CONVERSIONS, DIRECT_BUDGETS}), evaluate=evaluate,
    params=frozen({
        # ≤ 60% лимита за неделю: до 20–30% недотраты — обычное колебание аукциона и дней недели; 60% — кампания
        # системно не добирает почти половину денег, которые ей разрешили.
        "max_utilization_pct": 60,
        # CPA ≤ 90% ориентира: запас 10% — тот же порог отклонения, что у high_cpa (trigger_delta_pct = 10).
        "good_cpa_share": Decimal("0.9"),
        # ≥ 10 конверсий в окне: на меньшем CPA случаен (как current_high_conversions у high_cpa); ≥ 20 — medium.
        "min_conversions": 10,
        "medium_conversions": 20,
        "baseline_min_conversions": 10,  # как baseline у high_cpa (PRD §4.1)
    }),
)
