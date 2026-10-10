"""Аномалии (правило 5): резкий рост расхода или падение конверсий кампании относительно её собственной базы в этом
кабинете (30 дней до окна оценки). anomaly@1, за флагом audit_rules_candidates.

Два сигнала, один вывод на кампанию (issue_key = семейство + кампания); если сработали оба — в выводе тот, у
которого сумма больше, второй — в evidence_meta.signals:
  spend_spike     — расход за 7 дней ≥ spike_ratio × (средний дневной расход базы × 7), и расход сверх базы, не
                    объяснённый ростом конверсий по CPA базы, ≥ min_excess_rub;
  conversion_drop — по завершённым дням окна (date < partial_from, не меньше min_complete_days) конверсий ≤ drop_ratio
                    × ожидаемых по базе, при этом расход не упал ниже min_spend_ratio базы (иначе падение объяснено).
Сумма всегда estimated (формулы ниже): это оценка, а не факт потерь.

Действие — только «проверить причину» (изменения стратегии, бюджета, ставок, целей, сайта, сезонность): ставок и
бюджета правило не предлагает никогда, уровень inspect_only, достаточность данных не выше medium. Тип действия —
investigate_cpa_growth (уровень inspect_only и форма «проверить» уже есть в safety_policy и контракте API).

Досчёт конверсий: последние дни снимка (date ≥ partial_from) в конверсиях не участвуют — иначе каждое утро
выглядело бы падением. partial_from неизвестен — завершённых дней нет: падение не проверяется, рост расхода считается
без поправки на конверсии, достаточность low и level_reason = conversions_partial.

Пересечения: основа exposure — formula (блок «кампания × дни окна»). Выводы правил 1–4 по той же кампании за те же
дни exposure_total@1 берёт по максимуму, не суммой.

Недостаточно данных: история снимка короче окна + базы → BASELINE_HISTORY_INSUFFICIENT на весь кабинет; у кампании
с расходом ≥ min_excess_rub в окне база меньше min_active_days дней с расходом → BASELINE_DATA_INSUFFICIENT;
конверсии неизвестны (None) в базе или окне → SOURCE_MISSING."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.rules.domain import (BASELINE_DAYS, DIRECT_CONVERSIONS, EVALUATION_DAYS, FORMULA, AuditSettings, CampaignDay,
                              Fact, Finding, NotEnoughData, Output, Reason, Rule, SnapshotView, Window, frozen,
                              issue_key, windows)
from app.rules.evidence import PARTIAL, definition_meta, definition_missing, labels

FAMILY = "anomaly"
CENT = Decimal("0.01")
EXPECTED_COST_FORMULA = f"baseline_cost / {BASELINE_DAYS} * {EVALUATION_DAYS}"
CPA_FORMULA = "baseline_cost / baseline_conversions"
SPIKE_FORMULA = (f"cost - expected_cost - max(0, complete_conversions / complete_days - baseline_conversions / "
                 f"{BASELINE_DAYS}) * {EVALUATION_DAYS} * baseline_cpa")
EXPECTED_CONV_FORMULA = f"baseline_conversions / {BASELINE_DAYS} * complete_days"
DROP_FORMULA = "complete_cost - complete_conversions * baseline_cpa"
CHECKS = ("strategy", "conversion_goals")


@dataclass(frozen=True)
class Base:
    cost: Decimal
    conversions: Decimal
    cpa: Decimal | None  # None: конверсий в базе меньше baseline_min_conversions
    active_days: int


@dataclass(frozen=True)
class Signal:
    reason_code: str
    metric: str
    actual: Decimal
    reference: Decimal
    lost: Fact
    quality: str
    evidence: dict
    partial: bool = False


def _sum(days: list[CampaignDay], window: Window) -> tuple[Decimal, Decimal, int]:
    inside = [d for d in days if d.date in window]
    return (sum((d.cost for d in inside), Decimal(0)), sum((d.conversions or Decimal(0) for d in inside), Decimal(0)),
            len({d.date for d in inside}))


def _base(days: list[CampaignDay], baseline: Window, p) -> Base:
    cost, conv, _ = _sum(days, baseline)
    cpa = (cost / conv).quantize(CENT, ROUND_HALF_UP) if conv >= p["baseline_min_conversions"] and cost > 0 else None
    return Base(cost, conv, cpa, len({d.date for d in days if d.date in baseline and d.cost > 0}))


def _complete(snap: SnapshotView, evaluation: Window) -> Window | None:
    """Завершённые дни окна оценки: конверсии за них уже не досчитываются. None — таких нет."""
    if snap.partial_from is None or snap.partial_from <= evaluation.date_from:
        return None
    return Window(evaluation.date_from, min(snap.partial_from - timedelta(1), evaluation.date_to))


def _q(x: Decimal) -> Decimal:
    return x.quantize(CENT, ROUND_HALF_UP)


def _spike(rule: Rule, days, base: Base, evaluation: Window, done: Window | None) -> Signal | None:
    p, (conv_label, cpa_label) = rule.params, labels(rule)
    cost, _, _ = _sum(days, evaluation)
    expected = _q(base.cost / BASELINE_DAYS * EVALUATION_DAYS)
    if expected <= 0 or cost < expected * p["spike_ratio"]:
        return None
    backed, evidence = Decimal(0), {}
    if done is not None and base.cpa is not None:
        d_cost, d_conv, k = _sum(days, done)
        extra = max(Decimal(0), d_conv / k - base.conversions / BASELINE_DAYS) * EVALUATION_DAYS
        backed = extra * base.cpa
        evidence = {"complete_conversions": Fact(d_conv, "count", conv_label, done)}
    lost = _q(cost - expected - backed)
    if lost < p["min_excess_rub"]:
        return None  # рост объяснён конверсиями или слишком мал в рублях
    evidence |= {"cost": Fact(cost, "rub", "yandex_direct", evaluation),
                 "expected_cost": Fact(expected, "rub", "yandex_direct", evaluation, "estimated",
                                       EXPECTED_COST_FORMULA)}
    adjusted = done is not None and base.cpa is not None
    return Signal("spend_spike", "cost", cost, expected,
                  Fact(lost, "rub", cpa_label, evaluation, "estimated", SPIKE_FORMULA),
                  "medium" if adjusted else "low", evidence, partial=done is None)


def _drop(rule: Rule, days, base: Base, done: Window | None) -> Signal | None:
    p, (conv_label, cpa_label) = rule.params, labels(rule)
    if done is None or base.cpa is None:
        return None
    d_cost, d_conv, k = _sum(days, done)
    expected = _q(base.conversions / BASELINE_DAYS * k)
    if k < p["min_complete_days"] or expected < p["min_expected_conversions"]:
        return None  # ноль-два «пропавших» конверсии — обычный шум, а не аномалия
    if d_conv > expected * p["drop_ratio"] or d_cost < base.cost / BASELINE_DAYS * k * p["min_spend_ratio"]:
        return None  # конверсий не меньше половины ожидаемых или расход упал вместе с ними
    lost = _q(d_cost - d_conv * base.cpa)
    evidence = {"complete_cost": Fact(d_cost, "rub", "yandex_direct", done),
                "complete_conversions": Fact(d_conv, "count", conv_label, done),
                "expected_conversions": Fact(expected, "count", conv_label, done, "estimated",
                                             EXPECTED_CONV_FORMULA)}
    quality = "medium" if expected >= p["medium_expected_conversions"] else "low"
    return Signal("conversion_drop", "conversions", d_conv, expected,
                  Fact(lost, "rub", cpa_label, done, "estimated", DROP_FORMULA), quality, evidence)


def _finding(rule: Rule, snap: SnapshotView, campaign_id: int, s: Signal, base: Base, baseline: Window,
             signals: list[Signal]) -> Finding:
    conv_label, cpa_label = labels(rule)
    evidence = {**s.evidence, "baseline_cost": Fact(base.cost, "rub", "yandex_direct", baseline),
                "baseline_conversions": Fact(base.conversions, "count", conv_label, baseline)}
    if base.cpa is not None:
        evidence["baseline_cpa"] = Fact(base.cpa, "rub", cpa_label, baseline, "estimated", CPA_FORMULA)
    meta = {"signals": ",".join(x.reason_code for x in signals), **definition_meta(rule, snap),
            **(PARTIAL if s.partial else {})}
    return Finding(
        rule_version=rule.rule_version, issue_type=rule.family, object_type="campaign", object_id=campaign_id,
        issue_key=issue_key(snap.workspace_id, snap.direct_account_id, rule.family, "campaign", campaign_id),
        reason_code=s.reason_code, metric=s.metric, actual=s.actual, reference=s.reference, reference_type="baseline",
        delta_pct=((s.actual - s.reference) / s.reference * 100).quantize(Decimal("0.1"), ROUND_HALF_UP),
        lost=s.lost, recoverable=Fact.unavailable("rub", cpa_label, s.lost.period, reason="no_forecast"),
        current_data_quality=s.quality, evidence=frozen(evidence), evidence_meta=frozen(meta),
        action=frozen({"type": "investigate_cpa_growth", "check": CHECKS}), exposure_basis=FORMULA)


def _evaluate_campaign(rule: Rule, snap: SnapshotView, campaign_id: int, days: list[CampaignDay]) -> Output | None:
    p = rule.params
    evaluation, baseline = windows(snap.period_to)
    cost, _, _ = _sum(days, evaluation)
    if cost <= 0:
        return None
    if any(d.conversions is None for d in days if d.date in evaluation or d.date in baseline):
        return NotEnoughData(rule.rule_version, Reason.SOURCE_MISSING, "campaign", campaign_id)
    base = _base(days, baseline, p)
    if base.active_days < p["min_active_days"]:
        return (NotEnoughData(rule.rule_version, Reason.BASELINE_DATA_INSUFFICIENT, "campaign", campaign_id)
                if cost >= p["min_excess_rub"] else None)
    done = _complete(snap, evaluation)
    signals = [s for s in (_spike(rule, days, base, evaluation, done), _drop(rule, days, base, done)) if s]
    if not signals:
        return None
    top = max(signals, key=lambda s: s.lost.amount)
    return _finding(rule, snap, campaign_id, top, base, baseline, signals)


def evaluate(rule: Rule, snap: SnapshotView, settings: AuditSettings) -> tuple[Output, ...]:
    if missing := definition_missing(rule, snap):
        return missing
    if not snap.campaign_days:
        return ()
    _, baseline = windows(snap.period_to)
    if snap.period_from > baseline.date_from or min(d.date for d in snap.campaign_days) > baseline.date_from:
        return (NotEnoughData(rule.rule_version, Reason.BASELINE_HISTORY_INSUFFICIENT),)
    by_campaign: dict[int, list[CampaignDay]] = {}
    for day in snap.campaign_days:
        by_campaign.setdefault(day.campaign_id, []).append(day)
    results = (_evaluate_campaign(rule, snap, cid, days) for cid, days in sorted(by_campaign.items()))
    return tuple(r for r in results if r is not None)


# Пороги @1 — предложение до проверки на живых кабинетах (утверждает владелец; изменение = @2).
ANOMALY = Rule(
    id="anomaly", version=1, family=FAMILY, required_sources=frozenset({"yandex_direct", DIRECT_CONVERSIONS}),
    evaluate=evaluate,
    params=frozen({
        # +50% к базе за неделю: окно 7 дней усредняет дни недели, обычный разброс недельного расхода стабильной
        # кампании ±20–30% (аукцион, сезонность внутри месяца) — полтора раза уже за пределами этого шума.
        "spike_ratio": Decimal("1.5"),
        # Сверх базы ≥ 5 000 ₽ за 7 дней — тот же абсолютный минимум, что у zero_conv_campaign: меньшее не стоит
        # внимания владельца, а у маленьких кампаний +50% — это сотни рублей.
        "min_excess_rub": 5000,
        # База — ≥ 14 дней с расходом из 30: кампания, работавшая меньше полумесяца, своей «нормы» не имеет.
        "min_active_days": 14,
        # CPA базы — при ≥ 10 конверсиях, как baseline у high_cpa (PRD §4.1); иначе ни поправки, ни падения.
        "baseline_min_conversions": 10,
        # Падение: ≤ 50% ожидаемых конверсий при ожидании ≥ 10 (Пуассон: P(X ≤ 5 | λ = 10) ≈ 7%, при λ = 20 —
        # P(X ≤ 10) ≈ 1%: от 20 ожидаемых достаточность medium).
        "drop_ratio": Decimal("0.5"),
        "min_expected_conversions": 10,
        "medium_expected_conversions": 20,
        # Расход не ниже 80% базы: если расход упал так же, как конверсии, падение объяснено (меньше показов).
        "min_spend_ratio": Decimal("0.8"),
        # ≥ 3 завершённых дня: меньше — один выходной или праздник выглядел бы падением.
        "min_complete_days": 3,
    }),
)
