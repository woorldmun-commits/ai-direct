"""Стратегии кампании Директа и матрица рычагов STRATEGY_ACTIONS. Чистый модуль: без сети и БД (campaigns.py реэкспортирует)."""

from enum import Enum


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
