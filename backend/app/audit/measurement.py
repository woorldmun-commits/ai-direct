"""Методики замера эффекта выполненной рекомендации — чистые функции, как правила (ARCHITECTURE.md §5;
ECONOMICS.md §5.1 «Методики замера»). Дизайн сравнения у всех — DESIGN = uncontrolled_before_after: 7 дней до и
7 дней после дня выполнения (сам день — ни в одном окне), без контрольной группы. Методика выбирается по имени из
замера (measurements.policy = '<issue_type>_measure@N', его ставит триггер на 'done'): measure(policy, …).

observed effect (что произошло) и saved («Сэкономлено», что продукт вправе показать) — разные вещи. Любое сомнение —
saved = NULL. Схема БД: saved есть ⇔ verdict = effect; «изменение есть, экономия не подтверждена» — not_confirmed.
Входит ли saved в сумму «Сэкономлено ≈» — отдельно: counts_in_saved_total (только подтверждённое сверкой выполнение).

high_cpa: saved = конверсии_после × max(CPA_до − CPA_после, 0): расходы, сэкономленные на фактически полученном
объёме против прежнего CPA. Падение CPA за счёт урезанного объёма в saved не превращается.
- high_cpa_measure@2 — текущая: экономия подтверждается только при конверсиях_после ≥ конверсий_до; иначе
  verdict = not_confirmed («стоимость заявки снизилась, но экономия не подтверждена: заявок стало меньше»).
- high_cpa_measure@1 — историческая (допуск падения конверсий 20%, при падении — no_effect). Новые замеры по ней не
  создаются; остаётся для воспроизводимости уже сделанных.

zero_conv_campaign_measure@2 и zero_conv_placements_measure@2 — первые версии методик этих семейств. Номер «@2» —
тот, что ставит триггер create_measurement_on_done (schema.sql) для любого issue_type; «@1» у них нет и не было.
Критерии этих методик (помечены «утверждает владелец продукта») — в docstring их функций и в ECONOMICS.md §5.1."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Literal, Mapping

from app.rules.domain import CampaignDay, Fact, PlacementDay, Window, frozen

DESIGN = "uncontrolled_before_after"
_WAIT = {"final_data_wait_days": 14}  # сколько ждать окончательных данных за окно «после»; дальше — insufficient
# Параметры — часть версии: любое изменение — новая версия, старые замеры не пересчитываются.
_V1 = {
    "min_before_conversions": 3,     # меньше — CPA «до» слишком шумный, сравнивать не с чем
    # drop_pct = (conv_before − conv_after) / conv_before × 100; drop_pct > limit → saved = NULL
    "max_conversion_drop_pct": 20,
    "conversions_dropped_verdict": "no_effect",
    **_WAIT,
}
METHODS = {
    "high_cpa_measure@1": frozen(_V1),
    "high_cpa_measure@2": frozen({**_V1, "max_conversion_drop_pct": 0,  # conv_after ≥ conv_before
                                  "conversions_dropped_verdict": "not_confirmed"}),
    # CPA после ≤ max_cpa_after_reference_share × ориентир CPA выполненного вывода. Утверждает владелец продукта.
    "zero_conv_campaign_measure@2": frozen({"max_cpa_after_reference_share": Decimal(1), **_WAIT}),
    # Конверсии кампании «до» — не меньше: иначе «конверсии не упали» ничего не значит (0 → 0). Утверждает владелец.
    "zero_conv_placements_measure@2": frozen({"min_before_conversions": 3, **_WAIT}),
}
POLICY = "high_cpa_measure@2"  # high_cpa: по ней создаются новые замеры (триггер на 'done' в schema.sql)
PARAMS = METHODS[POLICY]
CENT = Decimal("0.01")
CPA_FORMULA = "period_total_spend / period_total_conversions"
SAVED_FORMULA = "conversions_after * (cpa_before - cpa_after)"
ZERO_CAMPAIGN_SAVED_FORMULA = "campaign_cost_before - campaign_cost_after"
PLACEMENTS_SAVED_FORMULA = "excluded_placements_cost_before - excluded_placements_cost_after"
DM = "yandex_direct+yandex_metrika"
Verdict = Literal["effect", "no_effect", "not_confirmed", "insufficient"]


@dataclass(frozen=True)
class Measured:
    verdict: Verdict
    before: Mapping[str, Fact]
    after: Mapping[str, Fact]
    saved: Fact | None
    effect: Mapping[str, str]  # reason + наблюдаемые изменения, строками (jsonb)


@dataclass(frozen=True)
class MeasureInput:
    """Всё, что методике нужно из снимка замера и из выполненного вывода (не из текущих настроек клиента)."""
    campaign_days: tuple[CampaignDay, ...]                 # только кампания выполненного вывода
    placement_days: tuple[PlacementDay, ...] = ()          # площадки этой кампании из снимка замера
    placements_reported: bool = False                      # в снимке замера есть отчёт площадок (direct_placements)
    placement_ids: frozenset[int] = frozenset()            # zero_conv_placements: какие площадки исключить (action)
    reference_cpa: Decimal | None = None                   # zero_conv_campaign: ориентир CPA выполненного вывода


def family(policy: str) -> str:
    return policy.rsplit("_measure@", 1)[0]


def _period(days: list[CampaignDay], window: Window) -> tuple[Decimal, Decimal, dict[str, Fact]]:
    inside = [d for d in days if d.date in window]
    cost = sum((d.cost for d in inside), Decimal(0))
    conv = sum((d.conversions or Decimal(0) for d in inside), Decimal(0))
    facts = {"cost": Fact(cost, "rub", "yandex_direct", window), "conversions": Fact(conv, "count", "yandex_metrika", window)}
    if conv > 0:
        facts["cpa"] = Fact((cost / conv).quantize(CENT, ROUND_HALF_UP), "rub", DM, window, "estimated", CPA_FORMULA)
    return cost, conv, facts


def _known(days: list[CampaignDay], *windows: Window) -> bool:
    """Конверсии известны за каждый день окон: ноль конверсий не выводится из их отсутствия (Метрика не подключена)."""
    return all(d.conversions is not None for d in days if any(d.date in w for w in windows))


def _pct(new: Decimal, old: Decimal) -> str:
    return str(((new - old) / old * 100).quantize(Decimal("0.1"), ROUND_HALF_UP))


def _money(amount: Decimal) -> str:
    return str(amount.quantize(CENT, ROUND_HALF_UP))


def _builder(b_facts: dict, a_facts: dict):
    def result(verdict: Verdict, reason: str, saved: Fact | None = None, **observed) -> Measured:
        return Measured(verdict, frozen(b_facts), frozen(a_facts), saved, frozen({"reason": reason, **observed}))
    return result


def measure_cpa(days: Iterable[CampaignDay], before: Window, after: Window, params=PARAMS) -> Measured:
    days = list(days)
    b_cost, b_conv, b_facts = _period(days, before)
    a_cost, a_conv, a_facts = _period(days, after)
    result = _builder(b_facts, a_facts)

    if b_conv < params["min_before_conversions"]:
        return result("insufficient", "before_conversions_below_minimum")
    if a_cost == 0 and a_conv == 0:
        return result("insufficient", "no_activity_after")  # кампанию остановили — эффект ставки не измерить
    if a_conv == 0:
        return result("no_effect", "no_conversions_after")
    cpa_b, cpa_a = b_cost / b_conv, a_cost / a_conv
    observed = {"cpa_change_pct": _pct(cpa_a, cpa_b), "conversions_change_pct": _pct(a_conv, b_conv)}
    if cpa_a >= cpa_b:
        return result("no_effect", "cpa_not_lower", **observed)
    if a_conv < b_conv * (1 - Decimal(params["max_conversion_drop_pct"]) / 100):
        return result(params["conversions_dropped_verdict"], "conversions_dropped", **observed)
    saved = Fact((a_conv * (cpa_b - cpa_a)).quantize(CENT, ROUND_HALF_UP), "rub", DM, after, "estimated", SAVED_FORMULA)
    return result("effect", "cpa_lower_at_same_volume", saved, **observed)


def measure_zero_conv_campaign(days: Iterable[CampaignDay], before: Window, after: Window,
                               reference_cpa: Decimal | None,
                               params=METHODS["zero_conv_campaign_measure@2"]) -> Measured:
    """Проблема — расход кампании без конверсий; действие — «проверить» (цели, стратегия, запросы). Эффект — появились
    ли конверсии и снизился ли расход без конверсий.

    saved = расход_до − расход_после (estimated, период — окно «после») — только если ВСЁ сразу:
      1) в окне «до» конверсий 0 (проблема была именно в окне сравнения; иначе — insufficient, сравнивать не с чем);
      2) расход_после < расход_до;
      3) конверсии_после > 0 — «не упали» при 0 → ≥ 0 выполняется всегда, поэтому этого мало: расход мог снизиться
         просто от урезанного бюджета, а деньги всё так же уходить впустую;
      4) CPA_после ≤ max_cpa_after_reference_share × ориентир CPA выполненного вывода (target_cpa или baseline-CPA из
         его evidence) — 1 конверсия на 30 000 ₽ при ориентире 3 000 ₽ всё ещё неэффективный расход. Ориентира нет
         (абсолютный порог правила) → экономию подтвердить нечем.
    Критерии 3–4 и share = 1 УТВЕРЖДАЕТ ВЛАДЕЛЕЦ ПРОДУКТА.
    Почему saved — снижение расхода, а не весь расход «до»: расход «после» при CPA не хуже ориентира уже приносит
    конверсии; «сэкономлено» — лишь то, что перестали тратить. Консервативно: эффективный расход «после» не вычитается.
    Ветки без saved: расход ниже, но конверсий нет → not_confirmed (spend_lower_still_no_conversions); конверсии
    появились, а расход не ниже → not_confirmed (conversions_appeared_spend_not_lower); CPA выше ориентира или
    ориентира нет → not_confirmed; конверсий нет и расход не ниже → no_effect; кампания остановлена (расход после 0) →
    insufficient (no_activity_after): остановка — не эффект проверки, а отказ от кампании, и её нельзя считать
    экономией без знания, нужна ли была кампания клиенту."""
    days = list(days)
    if not _known(days, before, after):
        return _builder({}, {})("insufficient", "conversions_unknown")
    b_cost, b_conv, b_facts = _period(days, before)
    a_cost, a_conv, a_facts = _period(days, after)
    result = _builder(b_facts, a_facts)

    if b_cost == 0:
        return result("insufficient", "no_spend_before")
    if b_conv > 0:
        return result("insufficient", "conversions_before")
    if a_cost == 0:
        return result("insufficient", "no_activity_after")
    observed = {"cost_change_pct": _pct(a_cost, b_cost), "conversions_after": str(a_conv)}
    if a_conv == 0:
        if a_cost < b_cost:
            return result("not_confirmed", "spend_lower_still_no_conversions", **observed)
        return result("no_effect", "no_conversions_after", **observed)
    if a_cost >= b_cost:
        return result("not_confirmed", "conversions_appeared_spend_not_lower", **observed)
    if reference_cpa is None or reference_cpa <= 0:
        return result("not_confirmed", "no_reference_cpa", **observed)
    cpa_a = a_cost / a_conv
    observed |= {"reference_cpa": _money(reference_cpa), "cpa_after_vs_reference_pct": _pct(cpa_a, reference_cpa)}
    if cpa_a > reference_cpa * params["max_cpa_after_reference_share"]:
        return result("not_confirmed", "cpa_after_above_reference", **observed)
    saved = Fact((b_cost - a_cost).quantize(CENT, ROUND_HALF_UP), "rub", DM, after, "estimated",
                 ZERO_CAMPAIGN_SAVED_FORMULA)
    return result("effect", "spend_lower_conversions_at_reference_cpa", saved, **observed)


def measure_zero_conv_placements(days: Iterable[CampaignDay], placement_days: Iterable[PlacementDay],
                                 placement_ids: frozenset[int], before: Window, after: Window, *,
                                 placements_reported: bool,
                                 params=METHODS["zero_conv_placements_measure@2"]) -> Measured:
    """Действие — исключить площадки (placement_ids выполненного вывода). P_до, P_после — расход ЭТИХ площадок в окнах;
    C — расход кампании, V — её конверсии.

    saved = P_до − P_после (estimated, период — окно «после») — только если ВСЁ сразу:
      1) P_до > 0 и P_после < P_до;
      2) V_после ≥ V_до, при V_до ≥ min_before_conversions (конверсии кампании в целом не упали; при V_до = 0 критерий
         ничего не проверяет — insufficient);
      3) C_после ≤ C_до − (P_до − P_после): расход кампании не вырос сверх «освободившейся» суммы. Иначе бюджет
         перетёк на другие площадки или поиск (Директ перераспределяет его сам) — деньги не сэкономлены, а потрачены
         иначе: verdict not_confirmed, reason budget_reallocated, saved = NULL. Частичную экономию (C_до − C_после)
         не засчитываем: снижение расхода кампании могло прийти от чего угодно, а не от исключения.
    Критерии 2–3 (в т. ч. min_before_conversions = 3 и «без допуска» в 3) УТВЕРЖДАЕТ ВЛАДЕЛЕЦ ПРОДУКТА.
    Нет отчёта площадок в снимке замера → insufficient (placements_not_in_snapshot): «площадки не тратили» не
    выводится из того, что их не смотрели. Конверсии неизвестны → insufficient. Кампания остановлена (C_после = 0) →
    insufficient (no_activity_after): экономия от остановки — не эффект исключения."""
    days = list(days)
    if not placements_reported:
        return _builder({}, {})("insufficient", "placements_not_in_snapshot")
    if not placement_ids:
        return _builder({}, {})("insufficient", "no_placements_in_action")
    if not _known(days, before, after):
        return _builder({}, {})("insufficient", "conversions_unknown")
    b_cost, b_conv, b_facts = _period(days, before)
    a_cost, a_conv, a_facts = _period(days, after)
    own = [p for p in placement_days if p.placement_id in placement_ids]
    p_before = sum((p.cost for p in own if p.date in before), Decimal(0))
    p_after = sum((p.cost for p in own if p.date in after), Decimal(0))
    b_facts["placements_cost"] = Fact(p_before, "rub", "yandex_direct", before)
    a_facts["placements_cost"] = Fact(p_after, "rub", "yandex_direct", after)
    result = _builder(b_facts, a_facts)

    if b_conv < params["min_before_conversions"]:
        return result("insufficient", "before_conversions_below_minimum")
    if p_before == 0:
        return result("insufficient", "no_placement_spend_before")
    if a_cost == 0:
        return result("insufficient", "no_activity_after")
    reduction = p_before - p_after
    observed = {"placements_cost_change_pct": _pct(p_after, p_before),
                "campaign_cost_change_pct": _pct(a_cost, b_cost), "conversions_change_pct": _pct(a_conv, b_conv)}
    if reduction <= 0:
        return result("no_effect", "placements_spend_not_lower", **observed)
    if a_conv < b_conv:
        return result("not_confirmed", "conversions_dropped", **observed)
    if a_cost > b_cost - reduction:
        return result("not_confirmed", "budget_reallocated",
                      reallocated=_money(min(a_cost - (b_cost - reduction), reduction)), **observed)
    saved = Fact(reduction.quantize(CENT, ROUND_HALF_UP), "rub", DM, after, "estimated",
                 PLACEMENTS_SAVED_FORMULA)
    return result("effect", "placements_spend_left_campaign", saved, **observed)


def measure(policy: str, data: MeasureInput, before: Window, after: Window) -> Measured:
    """Методика замера по её имени (с версией) — единственный вход для воркера. Неизвестное имя — KeyError: воркер
    проверяет METHODS заранее и пропускает такой замер (no_method_for_policy)."""
    params = METHODS[policy]
    kind = family(policy)
    if kind == "high_cpa":
        return measure_cpa(data.campaign_days, before, after, params)
    if kind == "zero_conv_campaign":
        return measure_zero_conv_campaign(data.campaign_days, before, after, data.reference_cpa, params)
    if kind == "zero_conv_placements":
        return measure_zero_conv_placements(data.campaign_days, data.placement_days, data.placement_ids, before,
                                            after, placements_reported=data.placements_reported, params=params)
    raise KeyError(policy)


def counts_in_saved_total(saved: object | None, execution_mode: str | None, verification_status: str | None) -> bool:
    """Входит ли saved замера в сумму «Сэкономлено ≈» (API_CONTRACT §7 counts_in_saved_total). v1.0: только ручное
    выполнение, подтверждённое сверкой по данным Директа (manual + confirmed). Неподтверждённое (pending,
    not_confirmed) показывает наблюдаемый эффект, но в сумму не входит; у «Проверил» (none) замера нет вовсе."""
    return saved is not None and execution_mode == "manual" and verification_status == "confirmed"
