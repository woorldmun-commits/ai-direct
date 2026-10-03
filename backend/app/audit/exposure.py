"""exposure_total@1 — итог «Расход с признаками неэффективности ≈» без двойного счёта (docs/ECONOMICS.md §3).

Чистая функция: без БД, сети, текущего времени; не импортирует ai/ и не знает конкретных правил. Вход — выводы
последнего аудита по каждому кабинету (их `lost` = exposure карточки) и строки статистики их снимков (`StatUnit`).
Уровень вывода берётся из `object_type` (ECONOMICS §3.2): `account` — кабинет, `campaign` — кампания, любой другой —
объект. Основу суммы декларирует правило (`ExposureBasis`, хранится в `findings.evidence_meta`, см. `basis_meta`):
- spend по уровню `campaign` — блок «кампания × дни окна» (вся кампания);
- spend по объектам (`level`, `object_ids`) — единицы: строки `stat_rows` этого уровня с этими object_id в дни окна
  (у вывода уровня кампании — только внутри неё; у объектного — `object_ids` = его объект);
- formula — блок со своей суммой на уровне кампании × дни окна.

Единица — кабинет · кампания · объект · день. Для каждой пары кабинет · кампания:
1. объектные выводы — объединение их единиц (одна единица — один раз). Уровни из ADDITIVE_LEVELS (запросы — поиск,
   площадки — сети) складываются как непересекающиеся; каждый другой уровень (час, регион, группа…) — своё
   измерение, и по одной кампании за один день измерения берутся по максимуму (§3.3 п. 1);
2. выводы уровня кампании — по максимуму, покрывают дни своего окна (`lost.period`);
3. в покрытые дни — max(вывод кампании, объектные единицы этих дней), в остальные — объектные как есть;
4. вклад пары не больше расхода кампании за эти дни (строки уровня `campaign`).
Затем вывод уровня кабинета против суммы вкладов его кампаний — по максимуму. Итог — сумма по кабинетам.

Решения там, где ECONOMICS не однозначен (минимальные, сохраняют инварианты §3.5):
- основа не угадывается по совпадению сумм: её декларирует правило. Вывод без декларации (записан до неё) — как
  formula: блок, а не единицы (итог не занижается и остаётся в границах §3.5, но пересечения с объектами того же
  дня вычитаются только по максимуму блока);
- spend по объектам, но сумма `cost` его строк в окне не равна `lost` (строк нет или данные расходятся) — тоже блок:
  иначе итог мог бы оказаться меньше карточки;
- блок объектного вывода, чьи строки не сводятся к одной кампании, добавляется к кабинету целиком, без вычета
  пересечений;
- несколько выводов кампании с разными окнами (§6 п. 4): сумма — максимум, покрытые дни — объединение окон;
- шаг 4 применяется, только если в снимке есть строки уровня `campaign` этой кампании; предел не опускается ниже
  самой большой карточки пары — иначе итог мог бы стать меньше карточки (гейт §3.5);
- карточки с `lost = unavailable` в итог не входят и считаются в `coverage.unavailable`; нет ни одной карточки с
  суммой → `total` и `overlap` — `unavailable` (не 0);
- `Value.snapshot_id` итога — самый новый снимок среди выводов (полный список — `snapshot_ids`); `data_status` —
  `partial`, если `partial` хоть у одного вывода; `coverage` — счётчики (целые, API_CONTRACT §1), а не `Value`.

Разложение по карточкам (`cards`, API: `exposure_overlap` карточки): итог каждой пары кабинет · кампания делится
между её карточками жадно — сначала самая большая (по своей части в паре), затем следующие, пока не исчерпан вклад
пары; итог кабинета — карточкам кабинета (если его вывод больше суммы кампаний) или кампаниям. Доля карточки ≤ её
суммы, overlap карточки = сумма − доля ≥ 0, и Σ (сумма − overlap) = total. Карточка без суммы — overlap unavailable."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from app.contract import SOURCES, Value
from app.rules.domain import ExposureBasis

VERSION = "exposure_total@1"
FORMULA = ("Σ по кабинетам max(вывод кабинета, Σ по кампаниям min(расход кампании, "
           "max(вывод кампании, объекты в его дни) + объекты в остальные дни))")
COMPONENT_FORMULA = "Σ сумм карточек типа (до вычета пересечений)"
OVERLAP_FORMULA = "Σ components - total"
CARD_OVERLAP_FORMULA = "сумма карточки - её доля в total (часть, уже учтённая другой карточкой)"

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
    basis: ExposureBasis | None = None  # None — вывод записан до декларации основы: считается как formula
    ref: object = None  # идентификатор карточки у вызывающего (id рекомендации) — ключ разложения `cards`


def basis_meta(basis: ExposureBasis) -> dict[str, str]:
    """Декларация основы → ключи findings.evidence_meta (строки, как остальные meta; id — через запятую)."""
    meta = {"exposure_basis": basis.kind}
    if basis.level is not None:
        meta["exposure_level"] = basis.level
    if basis.object_ids:
        meta["exposure_object_ids"] = ",".join(map(str, basis.object_ids))
    return meta


def basis_from_meta(meta: dict) -> ExposureBasis | None:
    """Обратно из evidence_meta; нет декларации или она не разбирается — None (старый вывод → как formula)."""
    if meta.get("exposure_basis") not in ("spend", "formula"):
        return None
    try:
        ids = tuple(int(x) for x in str(meta.get("exposure_object_ids") or "").split(",") if x)
        return ExposureBasis(meta["exposure_basis"], meta.get("exposure_level"), ids)
    except ValueError:
        return None


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
class CardOverlap:
    """Часть суммы карточки, уже учтённая другой карточкой (в итог не вошла второй раз)."""
    ref: object
    overlap: Value


@dataclass(frozen=True)
class ExposureTotal:
    total: Value
    overlap: Value
    components: tuple[Component, ...]
    coverage: Coverage
    snapshot_ids: tuple[int, ...]
    cards: tuple[CardOverlap, ...] = ()
    version: str = VERSION
    formula: str = FORMULA


@dataclass
class _Pair:
    """Кабинет · кампания: блоки уровня кампании, покрытые ими дни, объектные единицы."""
    blocks: dict[int, Decimal] = field(default_factory=dict)  # карточка → её сумма блоком
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
    block = max(pair.blocks.values()) if pair.blocks else None
    contribution = (max(block, inside) if block is not None else inside) + outside
    if spend is not None:  # шаг 4: не больше расхода кампании за эти дни — но не меньше самой большой карточки
        days = pair.covered | set(day_value)
        cap = sum((c for d, c in spend.items() if d in days), Decimal(0))
        floor = max([*pair.blocks.values(), *pair.parts.values(), Decimal(0)])
        contribution = min(contribution, max(cap, floor))
    return contribution


def _allocate(amount: Decimal, shares: dict[int, Decimal], out: dict[int, Decimal]) -> None:
    """amount между карточками: самая большая доля — первой, каждая — не больше своей доли."""
    for card, share in sorted(shares.items(), key=lambda x: (-x[1], x[0])):
        take = min(share, amount)
        out[card] += take
        amount -= take


def _account_total(findings: list[tuple[int, ExposureFinding]], units: list[StatUnit],
                   shares: dict[int, Decimal]) -> Decimal:
    objects: dict[tuple[str, int], list[StatUnit]] = defaultdict(list)
    spend: dict[int, dict[date, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for u in units:
        if u.level == CAMPAIGN_LEVEL:
            spend[u.campaign_id][u.date] += u.cost
        else:
            objects[(u.level, u.object_id)].append(u)
    account_blocks: dict[int, Decimal] = {}
    unattributed = Decimal(0)
    unattributed_cards: dict[int, Decimal] = {}
    pairs: dict[int, _Pair] = defaultdict(_Pair)
    for card, f in findings:
        amount, days, basis = f.lost.amount, _days(f.lost), f.basis
        if f.object_type == ACCOUNT_LEVEL:
            account_blocks[card] = amount
            continue
        if basis is not None and basis.kind == "spend" and basis.level != CAMPAIGN_LEVEL:
            rows = [u for oid in sorted(set(basis.object_ids)) for u in objects[(basis.level, oid)]
                    if u.date in days and (f.object_type != CAMPAIGN_LEVEL or u.campaign_id == f.object_id)]
            if rows and sum((u.cost for u in rows), Decimal(0)) == amount:  # сумма = расход своих единиц
                for u in rows:
                    pair = pairs[u.campaign_id]
                    pair.units[(u.level, u.object_id, u.date)] = u.cost
                    pair.parts[card] += u.cost
                continue
        if f.object_type == CAMPAIGN_LEVEL:  # spend по кампании, formula, без декларации, нераскладываемый spend
            pairs[f.object_id].blocks[card] = amount
            pairs[f.object_id].covered |= days
            continue
        rows = [u for u in objects[(f.object_type, f.object_id)] if u.date in days]
        campaigns = {u.campaign_id for u in rows}
        if len(campaigns) == 1:  # формульный (или не декларированный) объектный вывод — блоком «кампания × окно»
            pair = pairs[campaigns.pop()]
            pair.blocks[card] = amount
            pair.covered |= days
        else:
            unattributed += amount
            unattributed_cards[card] = amount
    campaign_shares: dict[int, Decimal] = defaultdict(Decimal)
    campaigns_total = Decimal(0)
    for cid, p in sorted(pairs.items()):
        contribution = _pair_contribution(p, spend.get(cid))
        in_pair: dict[int, Decimal] = defaultdict(Decimal)
        for card, amount in [*p.blocks.items(), *p.parts.items()]:
            in_pair[card] += amount
        _allocate(contribution, in_pair, campaign_shares)
        campaigns_total += contribution
    for card, amount in unattributed_cards.items():
        campaign_shares[card] += amount
    campaigns_total += unattributed
    if account_blocks and max(account_blocks.values()) >= campaigns_total:  # вывод кабинета покрывает всё
        _allocate(max(account_blocks.values()), account_blocks, shares)
        return max(account_blocks.values())
    for card, amount in campaign_shares.items():
        shares[card] += amount
    return campaigns_total


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
    """Ни у одной карточки нет суммы: общая причина карточек, если она одна; иначе (и без карточек) — no_data."""
    reasons = {v.unavailable_reason for v in values}
    return Value(amount=None, unit="rub", source=_source(values) if values else "yandex_direct",
                 period_from=min((v.period_from for v in values), default=as_of),
                 period_to=max((v.period_to for v in values), default=as_of),
                 calculation_type="unavailable",
                 data_status="partial" if any(v.data_status == "partial" for v in values) else "complete",
                 data_sufficiency="insufficient", snapshot_id=max((v.snapshot_id for v in values), default=0),
                 rule_version=VERSION, formula=formula,
                 unavailable_reason=reasons.pop() if len(reasons) == 1 else "no_data")


def _key(f: ExposureFinding) -> tuple:
    return (f.account_id, f.object_type, f.object_id, f.issue_type, f.lost.model_dump_json(), repr(f.basis),
            repr(f.ref))


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
        cards = tuple(CardOverlap(f.ref, _unavailable([f.lost], as_of, CARD_OVERLAP_FORMULA)) for f in ordered)
        return ExposureTotal(total=_unavailable(values, as_of, FORMULA), overlap=_unavailable(values, as_of,
                             OVERLAP_FORMULA), components=(), coverage=coverage, snapshot_ids=snapshot_ids,
                             cards=cards)

    by_account: dict[int, list[tuple[int, ExposureFinding]]] = defaultdict(list)
    for card, f in enumerate(counted):
        by_account[f.account_id].append((card, f))
    units_by_account: dict[int, list[StatUnit]] = defaultdict(list)
    for u in units:
        units_by_account[u.account_id].append(u)
    shares: dict[int, Decimal] = defaultdict(Decimal)
    total = sum((_account_total(fs, units_by_account[a], shares) for a, fs in sorted(by_account.items())), Decimal(0))

    by_type: dict[str, list[Value]] = defaultdict(list)
    for f in counted:
        by_type[f.issue_type].append(f.lost)
    sums = {t: sum((v.amount for v in vs), Decimal(0)) for t, vs in by_type.items()}
    components = tuple(Component(t, _estimated(sums[t], by_type[t], COMPONENT_FORMULA))
                       for t in sorted(sums, key=lambda t: (-sums[t], t)))
    values = [f.lost for f in counted]
    cards = tuple(CardOverlap(f.ref, _estimated(f.lost.amount - shares[card], [f.lost], CARD_OVERLAP_FORMULA))
                  for card, f in enumerate(counted))
    cards += tuple(CardOverlap(f.ref, _unavailable([f.lost], as_of, CARD_OVERLAP_FORMULA))
                   for f in ordered if f.lost.amount is None)
    return ExposureTotal(total=_estimated(total, values, FORMULA),
                         overlap=_estimated(sum(sums.values(), Decimal(0)) - total, values, OVERLAP_FORMULA),
                         components=components, coverage=coverage, snapshot_ids=snapshot_ids, cards=cards)
