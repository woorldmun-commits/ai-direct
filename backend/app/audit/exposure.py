"""exposure_total@1 — итог «Расход с признаками неэффективности ≈» без двойного счёта (docs/ECONOMICS.md §3).

Чистая функция: без БД, сети, текущего времени; не импортирует ai/ и не знает конкретных правил. Вход — выводы
последнего аудита по каждому кабинету (их `lost` = exposure карточки) и строки статистики их снимков (`StatUnit`).
Уровень вывода берётся из `object_type` (ECONOMICS §3.2): `account` — кабинет, `campaign` — кампания, любой другой —
объект, чьи единицы — строки `stat_rows` того же уровня (`level = object_type`, `object_id`).

Единица — кабинет · кампания · объект · день. Для каждой пары кабинет · кампания:
1. объектные выводы — объединение их единиц (одна единица — один раз). Уровни из ADDITIVE_LEVELS (запросы — поиск,
   площадки — сети) складываются как непересекающиеся; каждый другой уровень (час, регион, группа…) — своё
   измерение, и по одной кампании за один день измерения берутся по максимуму (§3.3 п. 1);
2. выводы уровня кампании — по максимуму, покрывают дни своего окна (`lost.period`);
3. в покрытые дни — max(вывод кампании, объектные единицы этих дней), в остальные — объектные как есть;
4. вклад пары не больше расхода кампании за эти дни (строки уровня `campaign`).
Затем вывод уровня кабинета против суммы вкладов его кампаний — по максимуму. Итог — сумма по кабинетам.

Решения там, где ECONOMICS не однозначен (минимальные, сохраняют инварианты §3.5):
- раскладывается ли сумма объектного вывода на единицы, определяют данные, а не имя правила: сумма `cost` его единиц
  в окне вывода ровно равна `lost` → раскладывается («без конверсий»); иначе (формула) — блок со своей суммой на
  уровне кампании × дни окна, как вывод кампании; если его единицы не сводятся к одной кампании — блок добавляется к
  кабинету целиком, без вычета пересечений;
- несколько выводов кампании с разными окнами (§6 п. 4): сумма — максимум, покрытые дни — объединение окон;
- шаг 4 применяется, только если в снимке есть строки уровня `campaign` этой кампании; предел не опускается ниже
  самой большой карточки пары — иначе итог мог бы стать меньше карточки (гейт §3.5);
- карточки с `lost = unavailable` в итог не входят и считаются в `coverage.unavailable`; нет ни одной карточки с
  суммой → `total` и `overlap` — `unavailable` (не 0);
- `Value.snapshot_id` итога — самый новый снимок среди выводов (полный список — `snapshot_ids`); `data_status` —
  `partial`, если `partial` хоть у одного вывода; `coverage` — счётчики (целые, API_CONTRACT §1), а не `Value`."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from app.contract import SOURCES, Value

VERSION = "exposure_total@1"
FORMULA = ("Σ по кабинетам max(вывод кабинета, Σ по кампаниям min(расход кампании, "
           "max(вывод кампании, объекты в его дни) + объекты в остальные дни))")
COMPONENT_FORMULA = "Σ сумм карточек типа (до вычета пересечений)"
OVERLAP_FORMULA = "Σ components - total"

ACCOUNT_LEVEL = "account"
CAMPAIGN_LEVEL = "campaign"
# Не пересекаются по расходу: поиск и сети (ECONOMICS §3.3 п. 1; проверить на живых данных — §6 п. 1).
ADDITIVE_LEVELS = frozenset({"query", "placement"})
_ADDITIVE_GROUP = "query+placement"
CENT = Decimal("0.01")


@dataclass(frozen=True)
class ExposureFinding:
    """Карточка: кабинет, тип проблемы (семейство), объект и её exposure (`findings.lost`)."""
    account_id: int
    issue_type: str
    object_type: str
    object_id: int
    lost: Value


@dataclass(frozen=True)
class StatUnit:
    """Строка `stat_rows` снимка вывода: кабинет · кампания · уровень · объект · день → расход."""
    account_id: int
    campaign_id: int
    level: str
    object_id: int
    date: date
    cost: Decimal


@dataclass(frozen=True)
class Component:
    issue_type: str
    amount: Value


@dataclass(frozen=True)
class Coverage:
    included: int     # карточки с суммой — вошли в итог
    unavailable: int  # карточки без числа — в итог не вошли


@dataclass(frozen=True)
class ExposureTotal:
    total: Value
    overlap: Value
    components: tuple[Component, ...]
    coverage: Coverage
    snapshot_ids: tuple[int, ...]
    version: str = VERSION
    formula: str = FORMULA


@dataclass
class _Pair:
    """Кабинет · кампания: блоки уровня кампании, покрытые ими дни, объектные единицы."""
    blocks: list[Decimal] = field(default_factory=list)
    covered: set[date] = field(default_factory=set)
    units: dict[tuple[str, int, date], Decimal] = field(default_factory=dict)
    parts: dict[int, Decimal] = field(default_factory=lambda: defaultdict(Decimal))  # карточка → её часть в паре


def _days(v: Value) -> set[date]:
    return {v.period_from + timedelta(i) for i in range((v.period_to - v.period_from).days + 1)}


def _group(level: str) -> str:
    return _ADDITIVE_GROUP if level in ADDITIVE_LEVELS else level


def _pair_contribution(pair: _Pair, spend: dict[date, Decimal] | None) -> Decimal:
    by_day: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for (level, _, day), cost in pair.units.items():
        by_day[day][_group(level)] += cost
    day_value = {day: max(groups.values()) for day, groups in by_day.items()}
    inside = sum((v for d, v in day_value.items() if d in pair.covered), Decimal(0))
    outside = sum((v for d, v in day_value.items() if d not in pair.covered), Decimal(0))
    block = max(pair.blocks) if pair.blocks else None
    contribution = (max(block, inside) if block is not None else inside) + outside
    if spend is not None:  # шаг 4: не больше расхода кампании за эти дни — но не меньше самой большой карточки
        days = pair.covered | set(day_value)
        cap = sum((c for d, c in spend.items() if d in days), Decimal(0))
        floor = max([*pair.blocks, *pair.parts.values(), Decimal(0)])
        contribution = min(contribution, max(cap, floor))
    return contribution


def _account_total(findings: list[tuple[int, ExposureFinding]], units: list[StatUnit]) -> Decimal:
    objects: dict[tuple[str, int], list[StatUnit]] = defaultdict(list)
    spend: dict[int, dict[date, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for u in units:
        if u.level == CAMPAIGN_LEVEL:
            spend[u.campaign_id][u.date] += u.cost
        else:
            objects[(u.level, u.object_id)].append(u)
    account_blocks: list[Decimal] = []
    unattributed = Decimal(0)
    pairs: dict[int, _Pair] = defaultdict(_Pair)
    for card, f in findings:
        amount, days = f.lost.amount, _days(f.lost)
        if f.object_type == ACCOUNT_LEVEL:
            account_blocks.append(amount)
            continue
        if f.object_type == CAMPAIGN_LEVEL:
            pairs[f.object_id].blocks.append(amount)
            pairs[f.object_id].covered |= days
            continue
        rows = [u for u in objects[(f.object_type, f.object_id)] if u.date in days]
        if rows and sum((u.cost for u in rows), Decimal(0)) == amount:  # «без конверсий»: сумма = расход единиц
            for u in rows:
                pair = pairs[u.campaign_id]
                pair.units[(u.level, u.object_id, u.date)] = u.cost
                pair.parts[card] += u.cost
            continue
        campaigns = {u.campaign_id for u in rows}
        if len(campaigns) == 1:  # формульный объектный вывод — блоком «кампания × дни окна»
            pair = pairs[campaigns.pop()]
            pair.blocks.append(amount)
            pair.covered |= days
        else:
            unattributed += amount
    campaigns_total = sum((_pair_contribution(p, spend.get(cid)) for cid, p in sorted(pairs.items())), Decimal(0))
    campaigns_total += unattributed
    return max(max(account_blocks), campaigns_total) if account_blocks else campaigns_total


def _source(values: list[Value]) -> str:
    used = {s for v in values for s in v.source.split("+")}
    return "+".join(s for s in SOURCES if s in used)


def _estimated(amount: Decimal, values: list[Value], formula: str) -> Value:
    return Value(amount=amount.quantize(CENT), unit="rub", source=_source(values),
                 period_from=min(v.period_from for v in values), period_to=max(v.period_to for v in values),
                 calculation_type="estimated",
                 data_status="partial" if any(v.data_status == "partial" for v in values) else "complete",
                 data_sufficiency="sufficient", snapshot_id=max(v.snapshot_id for v in values),
                 rule_version=VERSION, formula=formula)


def _unavailable(values: list[Value], as_of: date, formula: str) -> Value:
    return Value(amount=None, unit="rub", source=_source(values) if values else "yandex_direct",
                 period_from=min((v.period_from for v in values), default=as_of),
                 period_to=max((v.period_to for v in values), default=as_of),
                 calculation_type="unavailable",
                 data_status="partial" if any(v.data_status == "partial" for v in values) else "complete",
                 data_sufficiency="insufficient", snapshot_id=max((v.snapshot_id for v in values), default=0),
                 rule_version=VERSION, formula=formula)


def _key(f: ExposureFinding) -> tuple:
    return (f.account_id, f.object_type, f.object_id, f.issue_type, f.lost.model_dump_json())


def exposure_total(findings: Iterable[ExposureFinding], units: Iterable[StatUnit], *, as_of: date) -> ExposureTotal:
    """Итог по карточкам и строкам их снимков. `as_of` — период итога, когда карточек нет вовсе (иначе — их период)."""
    ordered = sorted(findings, key=_key)  # перестановка входа не меняет результат
    for f in ordered:
        if f.lost.unit != "rub":
            raise ValueError(f"exposure: lost в рублях, получено {f.lost.unit}")
    counted = [f for f in ordered if f.lost.amount is not None]
    coverage = Coverage(included=len(counted), unavailable=len(ordered) - len(counted))
    snapshot_ids = tuple(sorted({f.lost.snapshot_id for f in ordered}))
    if not counted:
        values = [f.lost for f in ordered]
        return ExposureTotal(total=_unavailable(values, as_of, FORMULA), overlap=_unavailable(values, as_of,
                             OVERLAP_FORMULA), components=(), coverage=coverage, snapshot_ids=snapshot_ids)

    by_account: dict[int, list[tuple[int, ExposureFinding]]] = defaultdict(list)
    for card, f in enumerate(counted):
        by_account[f.account_id].append((card, f))
    units_by_account: dict[int, list[StatUnit]] = defaultdict(list)
    for u in units:
        units_by_account[u.account_id].append(u)
    total = sum((_account_total(fs, units_by_account[a]) for a, fs in sorted(by_account.items())), Decimal(0))

    by_type: dict[str, list[Value]] = defaultdict(list)
    for f in counted:
        by_type[f.issue_type].append(f.lost)
    sums = {t: sum((v.amount for v in vs), Decimal(0)) for t, vs in by_type.items()}
    components = tuple(Component(t, _estimated(sums[t], by_type[t], COMPONENT_FORMULA))
                       for t in sorted(sums, key=lambda t: (-sums[t], t)))
    values = [f.lost for f in counted]
    return ExposureTotal(total=_estimated(total, values, FORMULA),
                         overlap=_estimated(sum(sums.values(), Decimal(0)) - total, values, OVERLAP_FORMULA),
                         components=components, coverage=coverage, snapshot_ids=snapshot_ids)
