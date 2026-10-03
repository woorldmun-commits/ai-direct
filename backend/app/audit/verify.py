"""Сверка ручного выполнения по данным Директа (API_CONTRACT.md §3.2, §6.1; ARCHITECTURE.md §4.2).

Чистые функции без БД, сети и LLM. Вход — действие в форме audit/present.py (то, что видел пользователь в принятой
версии), параметры объекта до (before_state из `accepted` или из `manual_claimed` с reliability = reduced) и после
(чтение синхронизацией, sources/direct_params.py). Выход — Verification; событие пишет воркер.

Два шага:
1. verify(action, before, after) — что показало сравнение: confirmed · not_confirmed · pending.
2. settle(v, claimed_at, read_at) — правило сроков: not_confirmed до истечения окна остаётся pending.
verify_claim() — оба шага разом. Писать событие можно только при v.final (verification_confirmed /
verification_not_confirmed); pending события не даёт.

Таблица исходов verify (detail — закрытый список DETAILS):

| Действие | Условие | status | detail |
|---|---|---|---|
| любое | нет before (before_state NULL) | pending | no_before_state |
| любое | чтение after не удалось | pending | after_unavailable |
| неизвестная форма | — | pending | action_not_verifiable |
| decrease_bid | средняя ставка фраз (поиск или сети) снизилась | confirmed | expected_change |
| decrease_bid | ставки только выросли | not_confirmed | opposite_direction |
| decrease_bid | ставки не менялись, менялось другое (стратегия ушла с ручной и т. п.) | not_confirmed | irrelevant_change |
| decrease_bid | ничего не менялось | not_confirmed | no_change |
| decrease_bid | ставки не прочитаны (до или после), стратегия та же | pending | bids_unreadable |
| lower_cpa | сработал любой из рычагов действия: ставка ↓ (decrease_bid), целевая цена конверсии ↓ при той же стратегии (lower_target_cpa), сменились приоритетные цели или цель стратегии (check_conversion_goals) | confirmed | expected_change |
| lower_cpa | ни один рычаг не сработал, хотя бы один сдвинулся вверх | not_confirmed | opposite_direction |
| lower_cpa | ставки нужны для вывода, но не прочитаны | pending | bids_unreadable |
| lower_cpa | изменилось другое / ничего | not_confirmed | irrelevant_change / no_change |
| exclude_placements | все площадки действия есть в ExcludedSites after | confirmed | placements_excluded |
| exclude_placements | исключена часть площадок | not_confirmed | placements_partially_excluded |
| exclude_placements | ни одной | not_confirmed | no_change |
| exclude_placements | у площадки нет имени (null или маска) — сопоставить не с чем | pending | placement_names_unknown |
| investigate | изменилось что-то из проверяемого (checks): цели, стратегия, минус-фразы, площадки, статус показов | confirmed | relevant_change |
| investigate | ничего из проверяемого | pending | investigate_no_change |

Решения:
- Исключение площадок сверяется по конечному состоянию: «площадки X в ExcludedSites», before нужен только для
  факта already_excluded. Поэтому reduced reliability (before прочитан в момент отметки и уже содержит изменение)
  исключению площадок не мешает. Частичное исключение — not_confirmed (после окна): выигрыш считался по всем
  площадкам, «Сэкономлено» по частично сделанному завышало бы результат; в facts — сколько исключено из скольких.
- lower_cpa / decrease_bid сверяются по направлению (before → after). При reduced reliability изменение могло
  попасть уже в before — тогда «нет изменений» → not_confirmed; Verification.reliability = reduced, UI добавляет
  «сверка менее надёжна» (API_CONTRACT §3.3). Величина снижения не проверяется — только направление.
- investigate («проверить») не задаёт ожидаемого изменения: правило может оказаться ложным срабатыванием, и
  «ничего не менять» — законный исход. Поэтому без изменений — pending, не not_confirmed (§6.1: «тип действия не
  сверяется → остаётся pending»), и окно его не переводит. not_required — только для execution_mode = none
  («Проверил», §3.2), к ручному выполнению не применяется.

Правило сроков (settle): not_confirmed становится окончательным, только когда (а) прошло VERIFY_WINDOW_DAYS = 3 дня
с manual_claimed и (б) after прочитан не раньше этого момента. До того — pending (detail сохраняется, final =
False). Почему 3 дня: настройки Директа (стратегия, ExcludedSites, ставки) видны в Campaigns.get сразу после
сохранения, модерация их не задерживает — ждать надо не API, а человека: «Выполнено» часто нажимают до правки или
делают её частями. Синхронизация ежедневная → это 3 чтения; при сбоях чтения окно не истекает «молча» — нужно
успешное чтение после срока. Это меньше окна замера (7 дней): неподтверждённое выполнение известно до замера.
confirmed окончателен сразу. Открытый вопрос DATA_MODEL.md §11 п. 13."""

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import Decimal

from app.sources.direct_params import BidsSummary, ObjectParams, ParamsUnavailable
from app.sync.sanitize import MASK, sanitize_placement

CONFIRMED, NOT_CONFIRMED, PENDING = "confirmed", "not_confirmed", "pending"
STATUSES = (CONFIRMED, NOT_CONFIRMED, PENDING)
RELIABILITY = ("normal", "reduced")
DETAILS = ("expected_change", "opposite_direction", "irrelevant_change", "no_change", "bids_unreadable",
           "placements_excluded", "placements_partially_excluded", "placement_names_unknown", "relevant_change",
           "investigate_no_change", "no_before_state", "after_unavailable", "action_not_verifiable")
VERIFY_WINDOW_DAYS = 3
VERIFY_WINDOW = timedelta(days=VERIFY_WINDOW_DAYS)

# Что считается изменением по пунктам «проверить» (present.CHECKS); статус показов (state) — всегда.
_CHECK_PARAMS = {
    "conversion_goals": ("priority_goals", "search_goal", "network_goal"),
    "strategy": ("search_strategy", "network_strategy", "search_target_cpa", "network_target_cpa",
                 "search_strategy_params", "network_strategy_params", "search_goal", "network_goal",
                 "daily_budget", "bids"),
    "search_queries_negative_keywords": ("negative_keywords",),
    "network_placements": ("excluded_sites", "network_strategy"),
}


@dataclass(frozen=True)
class Verification:
    status: str                       # confirmed · not_confirmed · pending
    detail: str                       # DETAILS
    changed: tuple[str, ...] = ()     # какие параметры изменились (коды diff())
    reliability: str = "normal"       # reduced — before прочитан в момент отметки
    facts: dict[str, str] = field(default_factory=dict)  # прочитанные значения для payload события (строки)
    final: bool = True                # можно писать событие verification_*; settle() снимает для окна

    def __post_init__(self):
        if self.status not in STATUSES or self.detail not in DETAILS or self.reliability not in RELIABILITY:
            raise ValueError(f"verification {self.status}/{self.detail}/{self.reliability}")
        if self.status == PENDING and self.final:
            object.__setattr__(self, "final", False)  # pending никогда не окончателен

    @property
    def event_type(self) -> str | None:
        """Тип события сверки или None — писать нечего."""
        if not self.final:
            return None
        return {CONFIRMED: "verification_confirmed", NOT_CONFIRMED: "verification_not_confirmed"}[self.status]

    def to_payload(self) -> dict:
        return {"status": self.status, "detail": self.detail, "changed": list(self.changed),
                "reliability": self.reliability, "facts": dict(self.facts)}


def _s(v) -> str:
    return "null" if v is None else (format(v, "f") if isinstance(v, Decimal) else str(v))


def diff(before: ObjectParams, after: ObjectParams) -> tuple[str, ...]:
    """Коды изменившихся параметров. Ставки сравниваются, только если прочитаны в обоих снимках."""
    out = []
    if before.state != after.state:
        out.append("state")
    if before.status != after.status:
        out.append("status")
    if (before.daily_budget, before.daily_budget_mode) != (after.daily_budget, after.daily_budget_mode):
        out.append("daily_budget")
    for name in ("search", "network"):
        b, a = getattr(before, name), getattr(after, name)
        if (b is None) != (a is None) or (b and a and b.provider_type != a.provider_type):
            out.append(f"{name}_strategy")
            continue
        if b is None:
            continue
        if b.target_cpa != a.target_cpa:
            out.append(f"{name}_target_cpa")
        if b.goal_id != a.goal_id:
            out.append(f"{name}_goal")
        if dict(b.money) | {"AverageCpa": None, "Cpa": None} != dict(a.money) | {"AverageCpa": None, "Cpa": None}:
            out.append(f"{name}_strategy_params")
    if before.priority_goals != after.priority_goals:
        out.append("priority_goals")
    if (before.excluded_sites, before.excluded_sites_masked) != (after.excluded_sites, after.excluded_sites_masked):
        out.append("excluded_sites")
    if before.negative_keywords_signature != after.negative_keywords_signature:
        out.append("negative_keywords")
    if before.bids and after.bids and before.bids.signature != after.bids.signature:
        out.append("bids")
    return tuple(out)


def _direction(pairs: list[tuple[Decimal | None, Decimal | None]]) -> str:
    """down · up · mixed · same по парам (до, после); пары с None пропускаются."""
    moves = {("down" if a < b else "up") for b, a in pairs if b is not None and a is not None and a != b}
    return moves.pop() if len(moves) == 1 else ("mixed" if moves else "same")


def _bids_direction(b: BidsSummary | None, a: BidsSummary | None) -> str | None:
    """Направление средних ставок; None — ставки не прочитаны в одном из снимков."""
    if b is None or a is None:
        return None
    return _direction([(b.search_mean, a.search_mean), (b.network_mean, a.network_mean)])


def _target_direction(before: ObjectParams, after: ObjectParams) -> str:
    """Целевая цена конверсии — только где стратегия площадки не менялась (иначе это смена стратегии)."""
    pairs = []
    for name in ("search", "network"):
        b, a = getattr(before, name), getattr(after, name)
        if b and a and b.provider_type == a.provider_type:
            pairs.append((b.target_cpa, a.target_cpa))
    return _direction(pairs)


def _bid_facts(before: ObjectParams, after: ObjectParams) -> dict[str, str]:
    facts = {}
    for side in ("search", "network"):
        for label, p in (("before", before), ("after", after)):
            if p.bids is not None:
                facts[f"bids_{side}_mean_{label}"] = _s(getattr(p.bids, f"{side}_mean"))
            strat = getattr(p, side)
            if strat is not None and strat.target_cpa is not None:
                facts[f"{side}_target_cpa_{label}"] = _s(strat.target_cpa)
    return facts


def _no_change(changed, reliability, facts, opposite: bool = False) -> Verification:
    detail = "opposite_direction" if opposite else ("irrelevant_change" if changed else "no_change")
    return Verification(NOT_CONFIRMED, detail, changed, reliability, facts)


def _verify_bids(action, before, after, changed, reliability) -> Verification:
    """decrease_bid и lower_cpa: рычаги из action.levers (decrease_bid — один рычаг «ставка»)."""
    levers = ({"decrease_bid"} if action["type"] == "decrease_bid"
              else {lv.get("lever") for lv in action.get("levers") or ()})
    facts = _bid_facts(before, after)
    moves = []
    bids_unknown = False
    if "decrease_bid" in levers:
        d = _bids_direction(before.bids, after.bids)
        manual_before = any(s is not None and s.manual for s in (before.search, before.network))
        strategy_same = not {"search_strategy", "network_strategy"} & set(changed)
        bids_unknown = d is None and manual_before and strategy_same
        moves.append(d)
    if "lower_target_cpa" in levers:
        moves.append(_target_direction(before, after))
    goals = "check_conversion_goals" in levers and bool(
        {"priority_goals", "search_goal", "network_goal"} & set(changed))
    if goals or any(m in ("down", "mixed") for m in moves):
        return Verification(CONFIRMED, "expected_change", changed, reliability, facts)
    if bids_unknown:
        return Verification(PENDING, "bids_unreadable", changed, reliability, facts)
    return _no_change(changed, reliability, facts, opposite="up" in moves)


def _verify_placements(action, before, after, changed, reliability) -> Verification:
    names = [p.get("name") for p in action.get("placements") or ()]
    if not names or any(not n or sanitize_placement(n) == MASK for n in names):
        return Verification(PENDING, "placement_names_unknown", changed, reliability,
                            {"placements_total": str(len(names))})
    target = {sanitize_placement(n) for n in names}
    done = target & set(after.excluded_sites)
    facts = {"placements_total": str(len(target)), "placements_excluded": str(len(done)),
             "placements_already_excluded": str(len(target & set(before.excluded_sites)))}
    if done == target:
        return Verification(CONFIRMED, "placements_excluded", changed, reliability, facts)
    if done:
        return Verification(NOT_CONFIRMED, "placements_partially_excluded", changed, reliability, facts)
    return Verification(NOT_CONFIRMED, "no_change", changed, reliability, facts)


def _verify_investigate(action, changed, reliability) -> Verification:
    relevant = {"state"}
    for check in action.get("checks") or ():
        relevant |= set(_CHECK_PARAMS.get(check, ()))
    hit = tuple(c for c in changed if c in relevant)
    if hit:
        return Verification(CONFIRMED, "relevant_change", changed, reliability)
    return Verification(PENDING, "investigate_no_change", changed, reliability)


def verify(action: dict, before: ObjectParams | None, after: ObjectParams | ParamsUnavailable | None,
           *, reliability: str = "normal") -> Verification:
    """Сравнение before/after по типу действия — таблица в docstring модуля. Без правила сроков (см. settle)."""
    if reliability not in RELIABILITY:
        raise ValueError(f"reliability {reliability!r}")
    if before is None:
        return Verification(PENDING, "no_before_state", reliability=reliability)
    if after is None or isinstance(after, ParamsUnavailable):
        facts = {"reason": after.reason} if isinstance(after, ParamsUnavailable) else {}
        return Verification(PENDING, "after_unavailable", reliability=reliability, facts=facts)
    if before.campaign_id != after.campaign_id:
        raise ValueError(f"сверка разных объектов: {before.campaign_id} ≠ {after.campaign_id}")
    changed = () if before.params_hash == after.params_hash else diff(before, after)
    kind = action.get("type") if isinstance(action, dict) else None
    if kind in ("decrease_bid", "lower_cpa"):
        return _verify_bids(action, before, after, changed, reliability)
    if kind == "exclude_placements":
        return _verify_placements(action, before, after, changed, reliability)
    if kind == "investigate":
        return _verify_investigate(action, changed, reliability)
    return Verification(PENDING, "action_not_verifiable", changed, reliability)


def settle(v: Verification, claimed_at: datetime, read_at: datetime | None,
           window: timedelta = VERIFY_WINDOW) -> Verification:
    """Правило сроков: not_confirmed окончателен, только если after прочитан не раньше claimed_at + window."""
    if v.status != NOT_CONFIRMED:
        return v
    if read_at is not None and read_at >= claimed_at + window:
        return v
    return replace(v, final=False)


def verify_claim(action: dict, before: ObjectParams | None, after: ObjectParams | ParamsUnavailable | None,
                 *, claimed_at: datetime, reliability: str = "normal") -> Verification:
    """verify + settle: то, что вызывает воркер сверки. read_at берётся из after."""
    v = verify(action, before, after, reliability=reliability)
    read_at = after.read_at if isinstance(after, ObjectParams) else None
    return settle(v, claimed_at, read_at)
