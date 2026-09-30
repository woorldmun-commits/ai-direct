"""Контекст кампании Директа (Campaigns.get): тип кампании, стратегии поиска и сетей, цели — нормализованно.

Стратегия хранится двумя величинами: provider_type — как ответил API (AVERAGE_CPA), strategy — наш enum. API
расширяется: новое значение даёт Strategy.UNKNOWN, а не падение, и политика тогда разрешает только наблюдение.

Матрица STRATEGY_ACTIONS — продуктовый контракт «какой рычаг есть у кампании и какой уровень действия по нему
допустим» (ARCHITECTURE.md §4.1). Пока это данные, а не решение: в выводы и политику контекст войдёт вместе с
safety_policy@2 — после проверки на реальных ответах API. Запись (Campaigns.update) не делаем.

Деньги в Campaigns.get — в микро-единицах валюты (× 1 000 000), в отличие от Reports API (returnMoneyInMicros: false)."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

import httpx

CAMPAIGNS_URL = {"api": "https://api.direct.yandex.com/json/v5/campaigns",
                 "sandbox": "https://api-sandbox.direct.yandex.com/json/v5/campaigns"}
SOURCE = "campaigns.get@v5"
_TYPE_FIELDS = {"TEXT_CAMPAIGN": "TextCampaign", "UNIFIED_CAMPAIGN": "UnifiedCampaign"}
_TYPE_FIELD_NAMES = ["BiddingStrategy", "PriorityGoals", "CounterIds"]
MICROS = Decimal(1_000_000)


class Strategy(str, Enum):
    MANUAL_BIDDING = "manual_bidding"          # ручные ставки
    AUTO_CLICKS = "auto_clicks"                # максимум кликов
    AUTO_CPC = "auto_cpc"                      # средняя цена клика
    AUTO_CPA = "auto_cpa"                      # средняя цена конверсии — целевой CPA
    PAY_FOR_CONVERSION = "pay_for_conversion"  # оплата за конверсии
    MAX_CONVERSIONS = "max_conversions"        # максимум конверсий
    SERVING_OFF = "serving_off"                # показы на площадке отключены
    UNSUPPORTED = "unsupported"                # известна, но продукт с ней не работает (ДРР, пакет кликов)
    UNKNOWN = "unknown"                        # API вернул то, чего мы не знаем


_PROVIDER_STRATEGY = {
    "HIGHEST_POSITION": Strategy.MANUAL_BIDDING,   # поиск: ручное управление ставками
    "MAXIMUM_COVERAGE": Strategy.MANUAL_BIDDING,   # сети: ручное управление ставками
    "WB_MAXIMUM_CLICKS": Strategy.AUTO_CLICKS,
    "AVERAGE_CPC": Strategy.AUTO_CPC,
    "AVERAGE_CPA": Strategy.AUTO_CPA,
    "PAY_FOR_CONVERSION": Strategy.PAY_FOR_CONVERSION,
    "WB_MAXIMUM_CONVERSION_RATE": Strategy.MAX_CONVERSIONS,
    "SERVING_OFF": Strategy.SERVING_OFF,
    "AVERAGE_CRR": Strategy.UNSUPPORTED,
    "PAY_FOR_CONVERSION_CRR": Strategy.UNSUPPORTED,
    "WEEKLY_CLICK_PACKAGE": Strategy.UNSUPPORTED,
}
# Объект параметров стратегии в ответе и поле цены конверсии в нём
_TARGET_FIELD = {"AVERAGE_CPA": ("AverageCpa", "AverageCpa"), "PAY_FOR_CONVERSION": ("PayForConversion", "Cpa")}

# Рычаг против высокого CPA и потолок уровня действия по нему. Потолок режет и политика по данным: при 1–2
# конверсиях всё равно inspect_only. change — «изменение допустимо, человек подтверждает», не автоприменение.
STRATEGY_ACTIONS: dict[Strategy, tuple[str | None, str]] = {
    Strategy.MANUAL_BIDDING: ("change_bid", "change"),
    Strategy.AUTO_CPA: ("change_target_cpa", "change"),
    Strategy.PAY_FOR_CONVERSION: ("change_conversion_price", "review"),  # меняет и объём, и оплату — только на проверку
    Strategy.MAX_CONVERSIONS: (None, "inspect_only"),  # цены конверсии нет — рычага против CPA нет, ставку не трогаем
    Strategy.AUTO_CLICKS: (None, "inspect_only"),
    Strategy.AUTO_CPC: (None, "inspect_only"),
    Strategy.SERVING_OFF: (None, "inspect_only"),
    Strategy.UNSUPPORTED: (None, "inspect_only"),
    Strategy.UNKNOWN: (None, "inspect_only"),
}


class DirectApiError(Exception):
    """Ответ {"error": ...}. Разбор кодов в классы доступа (AccountUnavailable и т. п.) — после сверки с песочницей."""

    def __init__(self, error_code: int, request_id: str | None):
        super().__init__(f"direct api error {error_code} (request {request_id})")
        self.error_code, self.request_id = error_code, request_id


@dataclass(frozen=True)
class StrategySide:
    provider_type: str             # как в API: AVERAGE_CPA; NETWORK_DEFAULT — «как на поиске»
    strategy: Strategy | None      # None: NETWORK_DEFAULT
    target_cpa: Decimal | None     # AUTO_CPA / PAY_FOR_CONVERSION: цена конверсии в валюте кампании
    goal_id: int | None


@dataclass(frozen=True)
class CampaignContext:
    campaign_id: int
    campaign_type: str             # TEXT_CAMPAIGN · UNIFIED_CAMPAIGN · …
    currency: str | None
    search: StrategySide | None    # None: тип кампании не поддержан — стратегия не читалась
    network: StrategySide | None
    priority_goals: tuple[int, ...]
    counter_ids: tuple[int, ...]
    source: str = SOURCE

    @property
    def strategy(self) -> Strategy:
        """Действующая стратегия кампании: одна на всех включённых площадках, иначе UNSUPPORTED (смешанная —
        единого рычага нет). Неподдержанный тип кампании — UNSUPPORTED."""
        if self.search is None or self.network is None:
            return Strategy.UNSUPPORTED
        search = self.search.strategy or Strategy.UNKNOWN  # NETWORK_DEFAULT на поиске не бывает
        network = search if self.network.strategy is None else self.network.strategy
        active = {s for s in (search, network) if s is not Strategy.SERVING_OFF}
        if not active:
            return Strategy.SERVING_OFF
        return active.pop() if len(active) == 1 else Strategy.UNSUPPORTED


def _side(raw: dict | None) -> StrategySide | None:
    if raw is None:
        return None
    provider = raw.get("BiddingStrategyType", "UNKNOWN")
    target = goal = None
    if provider in _TARGET_FIELD:
        obj, field = _TARGET_FIELD[provider]
        params = raw.get(obj) or {}
        target = Decimal(params[field]) / MICROS if params.get(field) is not None else None
        goal = params.get("GoalId")
    strategy = None if provider == "NETWORK_DEFAULT" else _PROVIDER_STRATEGY.get(provider, Strategy.UNKNOWN)
    return StrategySide(provider, strategy, target, goal)


def parse_campaign(c: dict) -> CampaignContext:
    specific = c.get(_TYPE_FIELDS.get(c["Type"], ""), {})
    bidding = specific.get("BiddingStrategy") or {}
    supported = c["Type"] in _TYPE_FIELDS
    return CampaignContext(
        campaign_id=int(c["Id"]), campaign_type=c["Type"], currency=c.get("Currency"),
        search=_side(bidding.get("Search")) if supported else None,
        network=_side(bidding.get("Network")) if supported else None,
        priority_goals=tuple(int(g["GoalId"]) for g in ((specific.get("PriorityGoals") or {}).get("Items") or ())),
        counter_ids=tuple(int(i) for i in ((specific.get("CounterIds") or {}).get("Items") or ())),
    )


def get_campaign_contexts(http: httpx.Client, access_token: str, client_login: str | None, campaign_ids: list[int],
                          *, env: str = "api") -> dict[int, CampaignContext]:
    """Только чтение. client_login — для агентских доступов (один клиент на запрос)."""
    headers = {"Authorization": f"Bearer {access_token}", "Accept-Language": "ru"}
    if client_login:
        headers["Client-Login"] = client_login
    body = {"method": "get", "params": {
        "SelectionCriteria": {"Ids": campaign_ids},
        "FieldNames": ["Id", "Type", "Currency"],
        **{f"{name}FieldNames": _TYPE_FIELD_NAMES for name in _TYPE_FIELDS.values()},
    }}
    r = http.post(CAMPAIGNS_URL[env], json=body, headers=headers, timeout=30)
    r.raise_for_status()  # 5xx и прочее без JSON-тела — не разбираем как ответ
    data = r.json()
    if "error" in data:
        raise DirectApiError(int(data["error"]["error_code"]), data["error"].get("request_id"))
    return {ctx.campaign_id: ctx for ctx in map(parse_campaign, data["result"].get("Campaigns", []))}
