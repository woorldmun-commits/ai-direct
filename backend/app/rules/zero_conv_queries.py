"""Поисковые запросы без конверсий (PRD §4, кандидат после v1.0 «минус-фразы»; правило 4). zero_conv_queries@1,
за флагом audit_rules_candidates.

Запрос попадает в вывод, если за окно оценки (7 дней) на нём потрачено не меньше min_cost_cpa_share × ориентир CPA,
было не меньше min_clicks кликов, а конверсий нет — ни в окне, ни за всю историю снимка (37 дней).

Гранулярность — кампания (как у площадок): один вывод «N запросов, ≈ X ₽», запросы — id в evidence и действии.
Текста запроса в правиле нет вовсе (QueryDay без текста): в вывод, шаблон уведомления и LLM уходят только id.

Действие — только «проверить» (кандидаты в минус-фразы): минус-фраза отрезает и будущие конверсии похожих
запросов, а ноль конверсий на 2 × CPA случается и у нормального запроса (e⁻² ≈ 14%). Решает человек, изменений нет.
Тип действия — investigate_zero_conversions с проверкой search_queries_negative_keywords: уровень inspect_only в
safety_policy и форма «проверить» в контракте API (свой тип потребует правки audit/policy.py и audit/present.py).

Основа exposure — spend по строкам уровня query с этими object_id внутри кампании за окно. Вывод zero_conv_campaign
по той же кампании покрывает весь её расход за те же дни: exposure_total@1 берёт максимум, а не сумму.
recoverable = unavailable (no_forecast): после минус-фраз Директ тратит бюджет на другие запросы.

Ориентир CPA — как у площадок: target_cpa, иначе CPA кампании за снимок при ≥ reference_min_conversions конверсиях.
Кампания без конверсий целиком — NO_CONVERSIONS (это правило 1, не запросы).

Досчёт конверсий (partial, последние дни снимка): запрос, который проходит пороги только с днями досчёта, остаётся в
выводе, но level_reason = conversions_partial и достаточность не выше medium. Конверсии запроса неизвестны (None) —
SOURCE_MISSING; запросы без конверсий есть, но ниже порогов — VOLUME_INSUFFICIENT (проблема не «исчезает»)."""

from datetime import date
from decimal import Decimal

from app.rules.domain import (DIRECT_CONVERSIONS, DIRECT_QUERIES, AuditSettings, CampaignDay, ExposureBasis, Fact,
                              Finding, NotEnoughData, Output, QueryDay, Reason, Rule, SnapshotView, Window, frozen,
                              issue_key, windows)
from app.rules.evidence import PARTIAL, definition_meta, definition_missing, labels, user_input
from app.rules.zero_conv_placements import _quality, _reference

FAMILY = "zero_conv_queries"
LOST_FORMULA = "sum(query_cost) for queries with 0 conversions, cost >= reference_cpa * min_cost_cpa_share, " \
               "clicks >= min_clicks"
CHECKS = ("search_queries_negative_keywords",)


def _passes(cost: Decimal, clicks: int, reference: Decimal, p) -> bool:
    return clicks >= p["min_clicks"] and cost >= reference * p["min_cost_cpa_share"]


def _flagged(days: list[QueryDay], reference: Decimal, evaluation: Window, partial_from: date | None, p):
    """(прошедшие пороги [(id, расход, клики, только_с_досчётом)] по убыванию расхода, причина «недостаточно данных»)."""
    by_query: dict[int, list[QueryDay]] = {}
    for d in days:
        by_query.setdefault(d.query_id, []).append(d)
    out, reasons = [], set()
    for qid, qdays in by_query.items():
        if any(d.conversions is not None and d.conversions > 0 for d in qdays):
            continue  # конверсия была хоть когда-то за снимок
        inside = [d for d in qdays if d.date in evaluation]
        cost, clicks = sum((d.cost for d in inside), Decimal(0)), sum(d.clicks for d in inside)
        if cost <= 0:
            continue
        if any(d.conversions is None for d in qdays):
            reasons.add(Reason.SOURCE_MISSING)
        elif not _passes(cost, clicks, reference, p):
            reasons.add(Reason.VOLUME_INSUFFICIENT)
        else:
            done = [d for d in inside if partial_from is not None and d.date < partial_from]
            solid = _passes(sum((d.cost for d in done), Decimal(0)), sum(d.clicks for d in done), reference, p)
            out.append((qid, cost, clicks, not solid))
    reason = (Reason.SOURCE_MISSING if Reason.SOURCE_MISSING in reasons
              else Reason.VOLUME_INSUFFICIENT if reasons else None)
    return sorted(out, key=lambda x: (-x[1], x[0])), reason


def _evaluate_campaign(rule: Rule, snap: SnapshotView, settings: AuditSettings, campaign_id: int,
                       campaign_days: list[CampaignDay], days: list[QueryDay]) -> Output | None:
    p = rule.params
    evaluation, _ = windows(snap.period_to)
    ref = _reference(rule, snap, settings, campaign_days, evaluation)
    if isinstance(ref, Reason):
        return NotEnoughData(rule.rule_version, ref, "campaign", campaign_id)
    reference, ref_evidence = ref
    flagged, reason = _flagged(days, reference, evaluation, snap.partial_from, p)
    if not flagged:
        return None if reason is None else NotEnoughData(rule.rule_version, reason, "campaign", campaign_id)

    cost = sum((f[1] for f in flagged), Decimal(0))
    partial = any(f[3] for f in flagged)
    mode = "target" if settings.target_cpa is not None else "campaign"
    conv_label, cpa_label = labels(rule)
    source = user_input(cpa_label) if mode == "target" else cpa_label
    evidence = {
        "cost": Fact(cost, "rub", "yandex_direct", evaluation),
        "clicks": Fact(Decimal(sum(f[2] for f in flagged)), "count", "yandex_direct", evaluation),
        "conversions": Fact(Decimal(0), "count", conv_label, Window(snap.period_from, snap.period_to)),
        "queries": Fact(Decimal(len(flagged)), "count", "yandex_direct", evaluation),
        **ref_evidence,
    }
    meta = {"reference_mode": mode, "query_ids": ",".join(str(f[0]) for f in flagged), **definition_meta(rule, snap),
            **(PARTIAL if partial else {})}
    for qid, q_cost, q_clicks, only_partial in flagged:
        evidence[f"query_{qid}_cost"] = Fact(q_cost, "rub", "yandex_direct", evaluation)
        evidence[f"query_{qid}_clicks"] = Fact(Decimal(q_clicks), "count", "yandex_direct", evaluation)
        if only_partial:
            meta[f"query_{qid}_status"] = "partial"
    return Finding(
        rule_version=rule.rule_version, issue_type=rule.family, object_type="campaign", object_id=campaign_id,
        issue_key=issue_key(snap.workspace_id, snap.direct_account_id, rule.family, "campaign", campaign_id),
        reason_code="queries_without_conversions", metric="query_cost_without_conversions",
        actual=cost, reference=reference, reference_type="target" if mode == "target" else "baseline",
        delta_pct=Decimal(0), lost=Fact(cost, "rub", source, evaluation, "estimated", LOST_FORMULA),
        recoverable=Fact.unavailable("rub", source, evaluation, reason="no_forecast"),
        current_data_quality=_quality(cost / reference, partial, p),
        evidence=frozen(evidence), evidence_meta=frozen(meta),
        action=frozen({"type": "investigate_zero_conversions", "check": CHECKS,
                       "query_ids": tuple(f[0] for f in flagged)}),
        exposure_basis=ExposureBasis("spend", "query", tuple(sorted(f[0] for f in flagged))),
    )


def evaluate(rule: Rule, snap: SnapshotView, settings: AuditSettings) -> tuple[Output, ...]:
    if missing := definition_missing(rule, snap):
        return missing
    evaluation, _ = windows(snap.period_to)
    queries: dict[int, list[QueryDay]] = {}
    for d in snap.query_days:
        queries.setdefault(d.campaign_id, []).append(d)
    campaigns: dict[int, list[CampaignDay]] = {}
    for d in snap.campaign_days:
        campaigns.setdefault(d.campaign_id, []).append(d)
    results = (_evaluate_campaign(rule, snap, settings, cid, campaigns.get(cid, []), days)
               for cid, days in sorted(queries.items())
               if any(d.date in evaluation and d.cost > 0 for d in days))
    return tuple(r for r in results if r is not None)


# Пороги @1 — предложение до проверки на живых кабинетах (утверждает владелец; изменение = @2).
ZERO_CONV_QUERIES = Rule(
    id="zero_conv_queries", version=1, family=FAMILY,
    required_sources=frozenset({"yandex_direct", DIRECT_CONVERSIONS, DIRECT_QUERIES}), evaluate=evaluate,
    params=frozen({
        # Расход запроса за 7 дней ≥ 2 × ориентир CPA: «нормальный» запрос дал бы ~2 конверсии, ноль случайно — e⁻² ≈
        # 14%. Строже площадок (1 × CPA): минус-фраза режет и будущий спрос, ошибка дороже, чем у исключённой площадки.
        "min_cost_cpa_share": Decimal("2"),
        # ≥ 30 кликов: при CR поиска 5% P(0 из 30) = 0,95³⁰ ≈ 21%, при 10% ≈ 4% — меньше кликов мало что говорят.
        "min_clicks": 30,
        # Ориентир — CPA кампании за снимок при ≥ 5 конверсиях, как у площадок (иначе порог «плавает»).
        "reference_min_conversions": 5,
        # Достаточность — ожидаемые конверсии на расходе выбранных запросов: ≥ 10 high, ≥ 3 medium (уровень всё
        # равно «проверить»: достаточность показывается человеку, действие не повышает).
        "high_expected_conversions": 10,
        "medium_expected_conversions": 3,
    }),
)
