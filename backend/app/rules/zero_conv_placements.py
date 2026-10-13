"""Площадки РСЯ без конверсий (STRATEGY.md §3, правило 3; PRD §4). zero_conv_placements@1.

Площадка сетей попадает в вывод, если за оцениваемое окно (7 дней) на ней потрачено не меньше ориентира CPA,
было не меньше min_clicks кликов, а конверсий нет — ни в окне, ни за всю историю снимка (37 дней).

Гранулярность — кампания, а не площадка: один вывод «N площадок, ≈ X ₽» с перечнем площадок в evidence.
- Шум: площадок в РСЯ сотни, расход каждой мал; вывод на площадку — десятки карточек по 300 ₽, которые вытеснили бы
  с экрана «Сегодня» (3 действия) всё остальное. Сумма по кампании — одно решение, сопоставимое с другими правилами.
- Действие и так одно на кампанию: список исключённых площадок в Директе — параметр кампании (ExcludedSites).
- Проблема живёт, пока в кампании есть такие площадки; состав списка меняется — issue_key тот же (кампания).
Для объединения расхода без двойного учёта (audit/exposure.py) в evidence есть каждая площадка отдельно:
placement_<id>_cost / _clicks за окно, а основа суммы декларирована явно: exposure_basis = spend по строкам уровня
placement с object_id из placement_ids внутри кампании вывода за окно lost.period.
recoverable = unavailable (no_forecast): после исключения площадок Директ перераспределяет бюджет на другие площадки,
а модели перераспределения в v1.0 нет — копия exposure завысила бы «Можно сэкономить».

Правило вычисляется, только если в снимке есть отчёт площадок (возможность direct_placements): без него площадок
«нет» не потому, что их проверили, — открытая проблема не должна закрыться как решённая. Если площадки без
конверсий с расходом в окне есть, но ни одна не проходит пороги — NotEnoughData(VOLUME_INSUFFICIENT), конверсии
площадки неизвестны (None) — NotEnoughData(SOURCE_MISSING): как у zero_conv_campaign, проблема не «исчезает» от того,
что расход упал ниже порога. Вывода нет (None) — только когда в окне нет расхода площадок без конверсий.

Ориентир CPA: target_cpa, если задан (user_input), иначе CPA самой кампании за весь снимок (37 дней, все сети и
поиск) — при не меньше reference_min_conversions конверсиях; иначе «недостаточно данных», а не выдуманный порог.

Досчёт конверсий (partial): конверсии последних дней ещё приходят. Площадка, которая проходит пороги только с учётом
дней досчёта, остаётся в выводе, но вывод помечается level_reason = conversions_partial, и достаточность данных не
выше medium (политика → не выше review). Действие — исключить площадки вручную в Директе; кандидат уровня review
(safety_policy: CANDIDATE_LEVEL["exclude_placements"] = "review"), change не бывает: исключение площадок меняет
охват кампании, и решение — за человеком.

@2 (те же пороги): источник конверсий и CPA — yandex_direct из реестра метрик; в evidence_meta — цели и атрибуция
снимка (без определения конверсии правило не вычисляется). Конверсии кампании неизвестны (None) — SOURCE_MISSING."""

from dataclasses import replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.rules.domain import (DIRECT_CONVERSIONS, DIRECT_PLACEMENTS, AuditSettings, CampaignDay, ExposureBasis,
                              Fact, Finding, NotEnoughData, Output, PlacementDay, Reason, Rule, SnapshotView, Window,
                              frozen, issue_key, windows)
from app.rules.evidence import definition_meta, definition_missing, labels, user_input

FAMILY = "zero_conv_placements"
CENT = Decimal("0.01")
MASK = "***"  # sync/sanitize.py: имя площадки не прошло allowlist — исключить такую площадку человек не сможет
CPA_FORMULA = "campaign_total_spend / campaign_total_conversions"
LOST_FORMULA = "sum(placement_cost) for placements with 0 conversions, cost >= reference_cpa * min_cost_cpa_share, " \
               "clicks >= min_clicks"
QUALITY_ORDER = ("low", "medium", "high")


def _sum_cost_conv(days, window: Window | None = None) -> tuple[Decimal, Decimal]:
    inside = [d for d in days if window is None or d.date in window]
    return (sum((d.cost for d in inside), Decimal(0)), sum((d.conversions for d in inside), Decimal(0)))


def _reference(rule: Rule, snap: SnapshotView, settings: AuditSettings, campaign_days: list[CampaignDay],
               evaluation: Window) -> tuple[Decimal, dict[str, Fact]] | Reason:
    if settings.target_cpa is not None:
        return settings.target_cpa, {"reference_cpa": Fact(settings.target_cpa, "rub", "user_input", evaluation)}
    period = Window(snap.period_from, snap.period_to)
    if any(d.conversions is None for d in campaign_days):
        return Reason.SOURCE_MISSING  # ноль конверсий не выводится из их отсутствия
    cost, conv = _sum_cost_conv(campaign_days)
    if conv == 0:
        return Reason.NO_CONVERSIONS  # кампания без конверсий целиком — это zero_conv_campaign, не площадки
    if conv < rule.params["reference_min_conversions"]:
        return Reason.BASELINE_DATA_INSUFFICIENT
    cpa = (cost / conv).quantize(CENT, ROUND_HALF_UP)
    if cpa <= 0:
        return Reason.BASELINE_DATA_INSUFFICIENT
    conv_label, cpa_label = labels(rule)
    return cpa, {
        "campaign_cost": Fact(cost, "rub", "yandex_direct", period),
        "campaign_conversions": Fact(conv, "count", conv_label, period),
        "reference_cpa": Fact(cpa, "rub", cpa_label, period, "estimated", CPA_FORMULA),
    }


def _passes(cost: Decimal, clicks: int, reference: Decimal, p) -> bool:
    return clicks >= p["min_clicks"] and cost >= reference * p["min_cost_cpa_share"]


def _flagged(days: list[PlacementDay], reference: Decimal, evaluation: Window, partial_from: date | None, p):
    """(прошедшие пороги, причина «недостаточно данных» или None). Прошедшие — (id, имя, расход, клики,
    только_с_досчётом) по убыванию расхода. Кандидат — площадка с именем, без конверсий за снимок и с расходом в окне:
    не прошла пороги → VOLUME_INSUFFICIENT; конверсии неизвестны → SOURCE_MISSING (ноль не выводится из отсутствия)."""
    by_placement: dict[int, list[PlacementDay]] = {}
    for d in days:
        by_placement.setdefault(d.placement_id, []).append(d)
    out, reasons = [], set()
    for pid, pdays in by_placement.items():
        name = next((d.placement for d in pdays if d.placement is not None), None)
        if name == MASK or any(d.conversions is not None and d.conversions > 0 for d in pdays):
            continue  # безымянная или с конверсиями хоть когда-то за снимок
        inside = [d for d in pdays if d.date in evaluation]
        cost, clicks = sum((d.cost for d in inside), Decimal(0)), sum(d.clicks for d in inside)
        if cost <= 0:
            continue
        if any(d.conversions is None for d in pdays):
            reasons.add(Reason.SOURCE_MISSING)
            continue
        if not _passes(cost, clicks, reference, p):
            reasons.add(Reason.VOLUME_INSUFFICIENT)
            continue
        complete = [d for d in inside if partial_from is not None and d.date < partial_from]
        solid = _passes(sum((d.cost for d in complete), Decimal(0)), sum(d.clicks for d in complete), reference, p)
        out.append((pid, name, cost, clicks, not solid))
    reason = (Reason.SOURCE_MISSING if Reason.SOURCE_MISSING in reasons
              else Reason.VOLUME_INSUFFICIENT if reasons else None)
    return sorted(out, key=lambda x: (-x[2], x[0])), reason


def _quality(expected_conversions: Decimal, partial: bool, p) -> str:
    """Достаточность данных: сколько конверсий «должно было быть» на этом расходе при ориентире CPA."""
    if expected_conversions >= p["high_expected_conversions"]:
        quality = "high"
    elif expected_conversions >= p["medium_expected_conversions"]:
        quality = "medium"
    else:
        quality = "low"
    if partial and quality == "high":
        quality = "medium"  # конверсии ещё досчитываются — не выше review
    return quality


def _evaluate_campaign(rule: Rule, snap: SnapshotView, settings: AuditSettings, campaign_id: int,
                       campaign_days: list[CampaignDay], days: list[PlacementDay]) -> Output | None:
    p = rule.params
    evaluation, _ = windows(snap.period_to)
    ref = _reference(rule, snap, settings, campaign_days, evaluation)
    if isinstance(ref, Reason):
        return NotEnoughData(rule.rule_version, ref, "campaign", campaign_id)
    reference, ref_evidence = ref
    flagged, reason = _flagged(days, reference, evaluation, snap.partial_from, p)
    if not flagged:
        return None if reason is None else NotEnoughData(rule.rule_version, reason, "campaign", campaign_id)

    cost = sum((f[2] for f in flagged), Decimal(0))
    clicks = sum(f[3] for f in flagged)
    partial = any(f[4] for f in flagged)
    mode = "target" if settings.target_cpa is not None else "campaign"
    conv_label, cpa_label = labels(rule)
    source = user_input(cpa_label) if mode == "target" else cpa_label
    evidence = {
        "cost": Fact(cost, "rub", "yandex_direct", evaluation),
        "clicks": Fact(Decimal(clicks), "count", "yandex_direct", evaluation),
        "conversions": Fact(Decimal(0), "count", conv_label, Window(snap.period_from, snap.period_to)),
        "placements": Fact(Decimal(len(flagged)), "count", "yandex_direct", evaluation),
        **ref_evidence,
    }
    meta = {"reference_mode": mode, "placement_ids": ",".join(str(f[0]) for f in flagged),
            **definition_meta(rule, snap)}
    for pid, name, p_cost, p_clicks, only_partial in flagged:
        evidence[f"placement_{pid}_cost"] = Fact(p_cost, "rub", "yandex_direct", evaluation)
        evidence[f"placement_{pid}_clicks"] = Fact(Decimal(p_clicks), "count", "yandex_direct", evaluation)
        if name is not None:
            meta[f"placement_{pid}_name"] = name
        if only_partial:
            meta[f"placement_{pid}_status"] = "partial"
    if partial:
        meta["level_reason"] = "conversions_partial"

    lost = Fact(cost, "rub", source, evaluation, "estimated", LOST_FORMULA)
    # «Можно сэкономить» — нет модели перераспределения бюджета после исключения площадок (v1.0): не копия lost
    recoverable = Fact.unavailable("rub", source, evaluation, reason="no_forecast")
    return Finding(
        rule_version=rule.rule_version, issue_type=rule.family, object_type="campaign", object_id=campaign_id,
        issue_key=issue_key(snap.workspace_id, snap.direct_account_id, rule.family, "campaign", campaign_id),
        reason_code="placements_without_conversions", metric="placement_cost_without_conversions",
        actual=cost, reference=reference, reference_type="target" if mode == "target" else "baseline",
        delta_pct=Decimal(0), lost=lost, recoverable=recoverable,
        current_data_quality=_quality(cost / reference, partial, p),
        evidence=frozen(evidence), evidence_meta=frozen(meta),
        action=frozen({"type": "exclude_placements", "execution": "manual",
                       "placement_ids": tuple(f[0] for f in flagged)}),
        exposure_basis=ExposureBasis("spend", "placement", tuple(sorted(f[0] for f in flagged))),
    )


def evaluate(rule: Rule, snap: SnapshotView, settings: AuditSettings) -> tuple[Output, ...]:
    if missing := definition_missing(rule, snap):
        return missing
    evaluation, _ = windows(snap.period_to)
    placements: dict[int, list[PlacementDay]] = {}
    for d in snap.placement_days:
        placements.setdefault(d.campaign_id, []).append(d)
    campaigns: dict[int, list[CampaignDay]] = {}
    for d in snap.campaign_days:
        campaigns.setdefault(d.campaign_id, []).append(d)
    results = (_evaluate_campaign(rule, snap, settings, cid, campaigns.get(cid, []), days)
               for cid, days in sorted(placements.items())
               if any(d.date in evaluation and d.cost > 0 for d in days))  # нет расхода в сетях — нечего проверять
    return tuple(r for r in results if r is not None)


# Пороги v1 утверждены владельцем 2026-10-03 (PRODUCT_SPEC §9.1). Любое изменение = новая версия правила.
ZERO_CONV_PLACEMENTS = Rule(
    id="zero_conv_placements", version=1, family=FAMILY,
    required_sources=frozenset({"yandex_direct", DIRECT_CONVERSIONS, DIRECT_PLACEMENTS}), evaluate=evaluate,
    params=frozen({
        # Расход площадки за 7 дней ≥ 1 × ориентир CPA: на этих деньгах кампания в среднем уже получила бы
        # одну конверсию. Ниже — ноль конверсий ничего не значит (у Пуассона с ожиданием 0,5 ноль в 61% случаев).
        "min_cost_cpa_share": Decimal("1"),
        # ≥ 20 кликов: дорогие клики (2–3 перехода на CPA) — слишком мало посетителей, чтобы судить о площадке.
        "min_clicks": 20,
        # CPA кампании — ориентир только при ≥ 5 конверсиях за 37 дней (иначе CPA случаен, порог «плавает»).
        "reference_min_conversions": 5,
        # Достаточность данных — ожидаемые конверсии на расходе выбранных площадок (расход / ориентир CPA):
        # ≥ 10 → high, ≥ 3 → medium (вероятность нуля случайно e^-3 ≈ 5%), меньше → low (политика → inspect_only).
        "high_expected_conversions": 10,
        "medium_expected_conversions": 3,
    }),
)

# @2 — те же пороги, другие метки источника и доказательства; @1 остаётся для старых выводов.
ZERO_CONV_PLACEMENTS_V2 = replace(ZERO_CONV_PLACEMENTS, version=2)
