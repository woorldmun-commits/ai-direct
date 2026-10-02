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
recoverable — своя формула, но это ВЕРХНЯЯ оценка: после исключения площадок Директ обычно перераспределяет бюджет
на другие площадки, и экономия будет меньше (formula это говорит).

Ориентир CPA: target_cpa, если задан (user_input), иначе CPA самой кампании за весь снимок (37 дней, все сети и
поиск) — при не меньше reference_min_conversions конверсиях; иначе «недостаточно данных», а не выдуманный порог.

Досчёт конверсий (partial): конверсии последних дней ещё приходят. Площадка, которая проходит пороги только с учётом
дней досчёта, остаётся в выводе, но вывод помечается level_reason = conversions_partial, и достаточность данных не
выше medium (политика → не выше review). Действие — исключить площадки вручную в Директе; кандидат уровня review
(safety_policy: CANDIDATE_LEVEL["exclude_placements"] = "review"), change не бывает: исключение площадок меняет
охват кампании, и решение — за человеком."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.rules.domain import (DIRECT_CONVERSIONS, AuditSettings, CampaignDay, ExposureBasis, Fact, Finding,
                              NotEnoughData, Output, PlacementDay, Reason, Rule, SnapshotView, Window, frozen, issue_key,
                              windows)

FAMILY = "zero_conv_placements"
CENT = Decimal("0.01")
MASK = "***"  # sync/sanitize.py: имя площадки не прошло allowlist — исключить такую площадку человек не сможет
CPA_FORMULA = "campaign_total_spend / campaign_total_conversions"
LOST_FORMULA = "sum(placement_cost) for placements with 0 conversions, cost >= reference_cpa * min_cost_cpa_share, " \
               "clicks >= min_clicks"
RECOVERABLE_FORMULA = ("upper bound: sum(placement_cost) of excluded placements over the window, "
                       "assuming the budget is not reallocated to other placements")
QUALITY_ORDER = ("low", "medium", "high")


def _sum_cost_conv(days, window: Window | None = None) -> tuple[Decimal, Decimal]:
    inside = [d for d in days if window is None or d.date in window]
    return (sum((d.cost for d in inside), Decimal(0)),
            sum((d.conversions or Decimal(0) for d in inside), Decimal(0)))


def _reference(rule: Rule, snap: SnapshotView, settings: AuditSettings, campaign_days: list[CampaignDay],
               evaluation: Window) -> tuple[Decimal, dict[str, Fact]] | Reason:
    if settings.target_cpa is not None:
        return settings.target_cpa, {"reference_cpa": Fact(settings.target_cpa, "rub", "user_input", evaluation)}
    period = Window(snap.period_from, snap.period_to)
    cost, conv = _sum_cost_conv(campaign_days)
    if conv == 0:
        return Reason.NO_CONVERSIONS  # кампания без конверсий целиком — это zero_conv_campaign, не площадки
    if conv < rule.params["reference_min_conversions"]:
        return Reason.BASELINE_DATA_INSUFFICIENT
    cpa = (cost / conv).quantize(CENT, ROUND_HALF_UP)
    if cpa <= 0:
        return Reason.BASELINE_DATA_INSUFFICIENT
    return cpa, {
        "campaign_cost": Fact(cost, "rub", "yandex_direct", period),
        "campaign_conversions": Fact(conv, "count", "yandex_metrika", period),
        "reference_cpa": Fact(cpa, "rub", "yandex_direct+yandex_metrika", period, "estimated", CPA_FORMULA),
    }


def _passes(cost: Decimal, clicks: int, reference: Decimal, p) -> bool:
    return clicks >= p["min_clicks"] and cost >= reference * p["min_cost_cpa_share"]


def _flagged(days: list[PlacementDay], reference: Decimal, evaluation: Window, partial_from: date | None, p):
    """Площадки кампании, прошедшие пороги: (id, имя, расход, клики, только_с_досчётом) по убыванию расхода."""
    by_placement: dict[int, list[PlacementDay]] = {}
    for d in days:
        by_placement.setdefault(d.placement_id, []).append(d)
    out = []
    for pid, pdays in by_placement.items():
        name = next((d.placement for d in pdays if d.placement is not None), None)
        if name == MASK or any(d.conversions is None or d.conversions > 0 for d in pdays):
            continue  # безымянная или с конверсиями хоть когда-то за снимок
        inside = [d for d in pdays if d.date in evaluation]
        cost, clicks = sum((d.cost for d in inside), Decimal(0)), sum(d.clicks for d in inside)
        if not _passes(cost, clicks, reference, p):
            continue
        complete = [d for d in inside if partial_from is not None and d.date < partial_from]
        solid = _passes(sum((d.cost for d in complete), Decimal(0)), sum(d.clicks for d in complete), reference, p)
        out.append((pid, name, cost, clicks, not solid))
    return sorted(out, key=lambda x: (-x[2], x[0]))


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
    flagged = _flagged(days, reference, evaluation, snap.partial_from, p)
    if not flagged:
        return None

    cost = sum((f[2] for f in flagged), Decimal(0))
    clicks = sum(f[3] for f in flagged)
    partial = any(f[4] for f in flagged)
    mode = "target" if settings.target_cpa is not None else "campaign"
    source = "yandex_direct+yandex_metrika" + ("+user_input" if mode == "target" else "")
    evidence = {
        "cost": Fact(cost, "rub", "yandex_direct", evaluation),
        "clicks": Fact(Decimal(clicks), "count", "yandex_direct", evaluation),
        "conversions": Fact(Decimal(0), "count", "yandex_metrika", Window(snap.period_from, snap.period_to)),
        "placements": Fact(Decimal(len(flagged)), "count", "yandex_direct", evaluation),
        **ref_evidence,
    }
    meta = {"reference_mode": mode, "placement_ids": ",".join(str(f[0]) for f in flagged)}
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
    recoverable = Fact(cost, "rub", source, evaluation, "estimated", RECOVERABLE_FORMULA)
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


# Пороги v1 — ПРЕДЛОЖЕНИЕ, утверждает владелец (PRODUCT_SPEC §10.1). Любое изменение = новая версия правила.
ZERO_CONV_PLACEMENTS = Rule(
    id="zero_conv_placements", version=1, family=FAMILY,
    required_sources=frozenset({"yandex_direct", DIRECT_CONVERSIONS}), evaluate=evaluate,
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
