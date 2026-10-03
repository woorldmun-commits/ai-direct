"""Текущие параметры объекта Директа для сверки ручного выполнения (API_CONTRACT.md §6.1, ARCHITECTURE.md §4.2).

Только чтение. OAuth-scope `direct:api` технически даёт и запись, поэтому граница держится кодом: DirectReadClient
вызывает только пары (сервис, метод) из READ_METHODS и проверяет это ДО сети — `campaigns.update`, `bids.set`,
`campaigns.suspend` и т. п. дают WriteMethodForbidden, запрос не уходит (тест: tests/test_direct_params.py).

Что читается (один Campaigns.get на кампанию, плюс KeywordBids.get только при ручной стратегии и действии про ставки):
стратегия поиска и сетей (тип, цена конверсии, средняя цена клика, недельный бюджет, потолок ставки, цель), дневной
бюджет, Status/State, приоритетные цели (PriorityGoals), исключённые площадки (ExcludedSites), минус-фразы — только
число и сигнатура (тексты не храним: before_state лежит в БД, а нам нужен лишь факт изменения), ставки ключевых фраз —
агрегатом (число, средняя ставка поиска и сетей, сигнатура).

Деньги: Campaigns.get и KeywordBids.get (API v5, JSON) отдают суммы в микро-единицах валюты (× 1 000 000) —
заголовок returnMoneyInMicros действует только в Reports API (sources/direct.py). Здесь — явная конвертация
micros → Decimal рубли с двумя знаками (как в sources/campaigns.py).

Ошибки доступа, токена, временные и формата → ParamsUnavailable(reason), а не исключение наверх: сверка тогда
остаётся pending (API_CONTRACT §6.1). Исключение наверх — только WriteMethodForbidden (ошибка программиста).

ПРОВЕРИТЬ на песочнице/живом аккаунте (ответы в тестах — по документации, MockTransport без сети):
- имена объектов параметров стратегии выводятся из BiddingStrategyType (AVERAGE_CPA → AverageCpa,
  WB_MAXIMUM_CONVERSION_RATE → WbMaximumConversionRate) — сверить для всех типов, особенно UNIFIED_CAMPAIGN;
- поля денег в параметрах стратегии (AverageCpa, Cpa, AverageCpc, WeeklySpendLimit, BidCeiling) и их наличие
  в UnifiedCampaign; PriorityGoals.Items[].Value — тоже микро-единицы?;
- ExcludedSites и NegativeKeywords — поля верхнего уровня Campaigns.get с {"Items": [...]}; у UNIFIED_CAMPAIGN
  минус-фразы могут жить в наборах (NegativeKeywordSharedSetIds) — сейчас не читаются;
- KeywordBids.get: SelectionCriteria.CampaignIds, SearchFieldNames/NetworkFieldNames = ["Bid"], форма ответа
  {"KeywordBids": [{"KeywordId", "Search": {"Bid"}, "Network": {"Bid"}}], "LimitedBy"}; ставки автотаргетинга
  и корректировки ставок (BidModifiers) не читаются;
- лимит страницы (10 000) и стоимость в баллах KeywordBids.get для больших кампаний."""

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import httpx

from app.sources.direct import (API_URL, DEFAULT_RETRY_IN, AccountUnavailable, ConnectionUnavailable, DirectApiError,
                                RetryLater, json_body, raise_for_direct_error)
from app.sync.sanitize import MASK, sanitize_placement

VERSION = "object_params@1"
SOURCE = "campaigns.get@v5"
BIDS_SOURCE = "keywordbids.get@v5"
MICROS = Decimal(1_000_000)
CENT = Decimal("0.01")
PAGE_LIMIT = 10_000
MAX_BID_PAGES = 10  # больше 100 000 фраз — ставки не сверяем (bids = None, bids_note = too_many_keywords)

# Allowlist методов чтения Direct API v5. Только `get`: всё остальное (add, update, delete, set, setAuto, suspend,
# resume, archive, unarchive, moderate, toggle…) — запись, в v1.0 запрещена (ARCHITECTURE §4.2, §11).
READ_METHODS: frozenset[tuple[str, str]] = frozenset({
    ("campaigns", "get"),
    ("keywordbids", "get"),
})

_TYPE_FIELDS = {"TEXT_CAMPAIGN": "TextCampaign", "UNIFIED_CAMPAIGN": "UnifiedCampaign"}
_MANUAL = frozenset({"HIGHEST_POSITION", "MAXIMUM_COVERAGE"})  # ручное управление ставками (поиск / сети)
_MONEY_FIELDS = ("AverageCpa", "Cpa", "AverageCpc", "WeeklySpendLimit", "BidCeiling")
_TARGET_CPA = {"AVERAGE_CPA": "AverageCpa", "PAY_FOR_CONVERSION": "Cpa"}

# Причины недоступности чтения: коды ошибок источника (sources/direct.py) и свои.
UNAVAILABLE_REASONS = frozenset({
    "token_expired", "token_revoked", "permission_missing",       # подключение
    "access_denied", "account_not_found", "api_restricted",       # аккаунт
    "api_unavailable",                                           # временно: сервер, баллы, соединения
    "api_error",                                                 # запрос отклонён (повтор не поможет)
    "campaign_not_found",                                        # кампании нет в ответе (удалена, чужая)
    "unsupported_campaign_type",                                 # стратегию такого типа не читаем
    "format_error",                                              # ответ не той формы
})


class WriteMethodForbidden(Exception):
    """Попытка вызвать метод Direct API вне allowlist чтения. Бросается до сети."""


class ParamsFormatError(ValueError):
    """Ответ API не той формы, что ожидает разбор."""


@dataclass(frozen=True)
class ParamsUnavailable:
    """Чтение не удалось — понятный результат вместо исключения. retry_in — для временных причин."""
    reason: str
    retry_in: int | None = None
    request_id: str | None = None

    def __post_init__(self):
        if self.reason not in UNAVAILABLE_REASONS:
            raise ValueError(f"reason {self.reason!r}")


@dataclass(frozen=True)
class StrategyParams:
    provider_type: str                          # как в API: AVERAGE_CPA, HIGHEST_POSITION, NETWORK_DEFAULT…
    goal_id: int | None = None
    money: tuple[tuple[str, Decimal], ...] = ()  # (поле API, рубли), отсортировано по полю

    @property
    def target_cpa(self) -> Decimal | None:
        name = _TARGET_CPA.get(self.provider_type)
        return dict(self.money).get(name) if name else None

    @property
    def manual(self) -> bool:
        return self.provider_type in _MANUAL


@dataclass(frozen=True)
class BidsSummary:
    """Ставки ключевых фраз агрегатом: без самих фраз и без поштучных ставок."""
    count: int
    search_mean: Decimal | None   # средняя ставка на поиске по фразам со ставкой; None — ставок нет
    network_mean: Decimal | None
    signature: str                # sha256 отсортированных (KeywordId, ставка поиска, ставка сетей)


@dataclass(frozen=True)
class ObjectParams:
    """Нормализованный снимок параметров кампании для сверки. params_hash — по содержимому, без read_at."""
    campaign_id: int
    campaign_type: str
    currency: str | None
    status: str | None                          # Status: ACCEPTED, DRAFT, MODERATION…
    state: str | None                           # State: ON, OFF, SUSPENDED, ENDED, ARCHIVED…
    daily_budget: Decimal | None
    daily_budget_mode: str | None
    search: StrategyParams | None               # None — тип кампании без поддерживаемой стратегии
    network: StrategyParams | None
    priority_goals: tuple[tuple[int, Decimal | None], ...]  # (GoalId, ценность в рублях), по GoalId
    excluded_sites: tuple[str, ...]             # нормализованные (sanitize_placement), отсортированы, без масок
    excluded_sites_masked: int                  # сколько значений ExcludedSites не прошло нормализацию
    negative_keywords_count: int
    negative_keywords_signature: str
    bids: BidsSummary | None = None             # None — не читались (не ручная стратегия / не нужно / не удалось)
    bids_note: str | None = None                # почему bids = None, если их пытались прочитать
    read_at: datetime | None = field(default=None, compare=False)
    version: str = VERSION

    def to_payload(self) -> dict:
        """JSON для payload.before_state / сверки: деньги строками, read_at ISO."""
        d = asdict(self)
        d["read_at"] = self.read_at.isoformat() if self.read_at else None
        return json.loads(json.dumps(d, default=_json_default))

    @classmethod
    def from_payload(cls, d: dict) -> "ObjectParams":
        if d.get("version") != VERSION:
            raise ValueError(f"before_state version {d.get('version')!r}")

        def side(s):
            if s is None:
                return None
            return StrategyParams(s["provider_type"], s.get("goal_id"),
                                  tuple((k, Decimal(v)) for k, v in s.get("money") or ()))

        b = d.get("bids")
        bids = None if b is None else BidsSummary(
            int(b["count"]), _dec(b["search_mean"]), _dec(b["network_mean"]), b["signature"])
        return cls(
            campaign_id=int(d["campaign_id"]), campaign_type=d["campaign_type"], currency=d.get("currency"),
            status=d.get("status"), state=d.get("state"), daily_budget=_dec(d.get("daily_budget")),
            daily_budget_mode=d.get("daily_budget_mode"), search=side(d.get("search")),
            network=side(d.get("network")),
            priority_goals=tuple((int(g), _dec(v)) for g, v in d.get("priority_goals") or ()),
            excluded_sites=tuple(d.get("excluded_sites") or ()),
            excluded_sites_masked=int(d.get("excluded_sites_masked") or 0),
            negative_keywords_count=int(d["negative_keywords_count"]),
            negative_keywords_signature=d["negative_keywords_signature"],
            bids=bids, bids_note=d.get("bids_note"),
            read_at=datetime.fromisoformat(d["read_at"]) if d.get("read_at") else None,
        )

    @property
    def params_hash(self) -> str:
        d = self.to_payload()
        d.pop("read_at")
        return _sha256(d)


def _json_default(o):
    if isinstance(o, Decimal):
        return format(o, "f")
    raise TypeError(type(o))


def _sha256(obj) -> str:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(raw.encode()).hexdigest()


def _dec(v) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def money(micros) -> Decimal | None:
    """Микро-единицы валюты (целое) → рубли Decimal с двумя знаками. None → None; иное — ParamsFormatError."""
    if micros is None:
        return None
    if isinstance(micros, bool) or not isinstance(micros, (int, str)):
        raise ParamsFormatError(f"сумма в микро-единицах: {type(micros).__name__}")
    try:
        value = Decimal(micros) if isinstance(micros, int) else Decimal(micros.strip())
    except InvalidOperation:
        raise ParamsFormatError("сумма в микро-единицах не число") from None
    if value != value.to_integral_value() or value < 0:
        raise ParamsFormatError("сумма в микро-единицах: не целое неотрицательное")
    return (value / MICROS).quantize(CENT, rounding=ROUND_HALF_UP)


def _params_object_name(provider_type: str) -> str:
    """AVERAGE_CPA → AverageCpa (имя объекта параметров стратегии в ответе; ПРОВЕРИТЬ для всех типов)."""
    return "".join(p.capitalize() for p in provider_type.split("_"))


def _strategy(raw) -> StrategyParams | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("BiddingStrategyType"), str):
        raise ParamsFormatError("BiddingStrategy: нет BiddingStrategyType")
    provider = raw["BiddingStrategyType"]
    params = raw.get(_params_object_name(provider)) or {}
    if not isinstance(params, dict):
        raise ParamsFormatError(f"параметры стратегии {provider}")
    amounts = tuple(sorted((f, money(params[f])) for f in _MONEY_FIELDS if params.get(f) is not None))
    goal = params.get("GoalId")
    return StrategyParams(provider, int(goal) if goal is not None else None, amounts)


def _items(obj) -> list:
    if obj is None:
        return []
    items = obj.get("Items") if isinstance(obj, dict) else None
    if items is None:
        return []
    if not isinstance(items, list):
        raise ParamsFormatError("Items не список")
    return items


def parse_campaign_params(c: dict, read_at: datetime | None = None) -> ObjectParams:
    """Объект Campaigns[i] ответа Campaigns.get → ObjectParams (без ставок). ParamsFormatError — не та форма."""
    try:
        ctype = c["Type"]
        specific = c.get(_TYPE_FIELDS.get(ctype, ""), {}) or {}
        bidding = specific.get("BiddingStrategy") or {}
        supported = ctype in _TYPE_FIELDS
        budget = c.get("DailyBudget") or {}
        sites, masked = set(), 0
        for raw in _items(c.get("ExcludedSites")):
            name = sanitize_placement(str(raw))
            if name == MASK:
                masked += 1
            else:
                sites.add(name)
        negatives = sorted(str(k) for k in _items(c.get("NegativeKeywords")))
        goals = tuple(sorted((int(g["GoalId"]), money(g.get("Value")))
                             for g in _items(specific.get("PriorityGoals"))))
        return ObjectParams(
            campaign_id=int(c["Id"]), campaign_type=ctype, currency=c.get("Currency"),
            status=c.get("Status"), state=c.get("State"),
            daily_budget=money(budget.get("Amount")), daily_budget_mode=budget.get("Mode"),
            search=_strategy(bidding.get("Search")) if supported else None,
            network=_strategy(bidding.get("Network")) if supported else None,
            priority_goals=goals, excluded_sites=tuple(sorted(sites)), excluded_sites_masked=masked,
            negative_keywords_count=len(negatives), negative_keywords_signature=_sha256(negatives),
            read_at=read_at,
        )
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        if isinstance(e, ParamsFormatError):
            raise
        raise ParamsFormatError(f"Campaigns.get: {type(e).__name__}") from None


def _mean(values: list[Decimal]) -> Decimal | None:
    return (sum(values) / len(values)).quantize(CENT, rounding=ROUND_HALF_UP) if values else None


def summarize_bids(rows: list[dict]) -> BidsSummary:
    """Строки KeywordBids → агрегат. Ставка 0 / нет ставки на площадке — не входит в среднее."""
    norm, search, network = [], [], []
    for r in rows:
        try:
            s = money((r.get("Search") or {}).get("Bid"))
            n = money((r.get("Network") or {}).get("Bid"))
            norm.append((int(r["KeywordId"]), s, n))
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            if isinstance(e, ParamsFormatError):
                raise
            raise ParamsFormatError(f"KeywordBids: {type(e).__name__}") from None
        if s:
            search.append(s)
        if n:
            network.append(n)
    norm.sort(key=lambda t: t[0])
    return BidsSummary(len(norm), _mean(search), _mean(network), _sha256(norm))


@dataclass(frozen=True)
class DirectReadClient:
    """Клиент Direct API v5 только для методов из READ_METHODS. http — app.sources.http.api_client("yandex_direct")."""
    http: httpx.Client
    access_token: str = field(repr=False)
    client_login: str | None = None
    env: str = "api"  # api · sandbox

    def call(self, service: str, method: str, params: dict) -> dict:
        """Вызов метода → объект result. Allowlist проверяется до сети. Ошибки — исключения sources/direct.py."""
        if (service, method) not in READ_METHODS:
            raise WriteMethodForbidden(f"{service}.{method}: вне allowlist методов чтения")
        headers = {"Authorization": f"Bearer {self.access_token}", "Accept-Language": "ru"}
        if self.client_login:
            headers["Client-Login"] = self.client_login
        try:
            r = self.http.post(f"{API_URL[self.env]}/v5/{service}", json={"method": method, "params": params},
                               headers=headers, timeout=30)
        except httpx.TransportError:
            raise RetryLater(DEFAULT_RETRY_IN, "api_unavailable") from None
        data = json_body(r)
        if r.status_code != 200 or "error" in data or not isinstance(data.get("result"), dict):
            raise_for_direct_error(r, self.client_login or "")
        return data["result"]


def needs_bids(action: dict) -> bool:
    """Нужны ли ставки фраз для сверки этого действия (формы audit/present.py)."""
    kind = action.get("type")
    if kind == "decrease_bid":
        return True
    if kind == "lower_cpa":
        return any(lv.get("lever") == "decrease_bid" for lv in action.get("levers") or ())
    return False


def _campaign_body(campaign_id: int) -> dict:
    return {
        "SelectionCriteria": {"Ids": [campaign_id]},
        "FieldNames": ["Id", "Type", "Currency", "Status", "State", "DailyBudget", "ExcludedSites",
                       "NegativeKeywords"],
        **{f"{name}FieldNames": ["BiddingStrategy", "PriorityGoals"] for name in _TYPE_FIELDS.values()},
    }


def _read_bids(client: DirectReadClient, campaign_id: int) -> tuple[BidsSummary | None, str | None]:
    rows: list[dict] = []
    offset = 0
    for _ in range(MAX_BID_PAGES):
        result = client.call("keywordbids", "get", {
            "SelectionCriteria": {"CampaignIds": [campaign_id]},
            "FieldNames": ["KeywordId"], "SearchFieldNames": ["Bid"], "NetworkFieldNames": ["Bid"],
            "Page": {"Limit": PAGE_LIMIT, "Offset": offset},
        })
        page = result.get("KeywordBids") or []
        if not isinstance(page, list):
            raise ParamsFormatError("KeywordBids не список")
        rows += page
        if result.get("LimitedBy") is None:
            return summarize_bids(rows), None
        offset = int(result["LimitedBy"])
    return None, "too_many_keywords"


def read_object_params(client: DirectReadClient, campaign_id: int, action: dict,
                       read_at: datetime) -> ObjectParams | ParamsUnavailable:
    """Параметры кампании, нужные для сверки действия. Ставки — только при ручной стратегии хотя бы на одной
    площадке и действии про ставки. Любая ошибка чтения → ParamsUnavailable (сверка останется pending)."""
    try:
        result = client.call("campaigns", "get", _campaign_body(campaign_id))
        campaigns = result.get("Campaigns") or []
        found = [c for c in campaigns if isinstance(c, dict) and str(c.get("Id")) == str(campaign_id)]
        if not found:
            return ParamsUnavailable("campaign_not_found")
        params = parse_campaign_params(found[0], read_at)
        if params.search is None and params.network is None:
            return ParamsUnavailable("unsupported_campaign_type")
        manual = any(s is not None and s.manual for s in (params.search, params.network))
        if needs_bids(action) and manual:
            bids, note = _read_bids(client, campaign_id)
            params = replace(params, bids=bids, bids_note=note)
        return params
    except (ConnectionUnavailable, AccountUnavailable) as e:
        return ParamsUnavailable(e.error_code)
    except RetryLater as e:
        return ParamsUnavailable("api_unavailable", retry_in=e.retry_in)
    except DirectApiError as e:
        return ParamsUnavailable("api_error", request_id=e.request_id)
    except ParamsFormatError:
        return ParamsUnavailable("format_error")
