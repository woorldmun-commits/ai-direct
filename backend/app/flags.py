"""Флаги функций — единственное место, где читаются их переменные окружения (имя флага в верхнем регистре:
CHIEF_ANALYST, LLM_ENABLED …). Умолчания — решения владельца продукта (Intelligence 2.0). Пустое или непонятное
значение оставляет умолчание: опечатка не включает и не выключает функцию."""

import logging
import os
from typing import Mapping

log = logging.getLogger(__name__)

DEFAULTS: Mapping[str, bool] = {
    "source_of_truth_v2": True,   # правила @2: источник конверсий и CPA — из реестра метрик
    "safety_engine_v2": True,     # safety_policy@2
    "chief_analyst": False,
    "root_cause": False,
    "llm_enabled": False,
    # правила @3 (rules.RULES_V3: статистический порог high_cpa, НДС target_cpa, CPA сетей для площадок): меняют, какие
    # выводы появляются (пример PRD §4.1 — 8 конверсий, +37% — шумом не отличим от нормы и вывода не даёт) — включает владелец
    "audit_rules_v3": False,
    "audit_rules_candidates": False,  # правила 4, 5 и бюджет (rules.FLAGGED) — до проверки на живых кабинетах
    "sms_login": False,           # вход по SMS: юридический HOLD (ст. 10 149-ФЗ), маршруты /auth/code/* выключены
}
SAFETY_FLAGS = ("safety_engine_v2", "source_of_truth_v2")  # их выключение возвращает старое, менее строгое поведение
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def flag(name: str, env: Mapping[str, str] | None = None) -> bool:
    default = DEFAULTS[name]  # неизвестный флаг — KeyError, а не False
    env = os.environ if env is None else env
    raw = env.get(name.upper(), "").strip().lower()
    return True if raw in _TRUE else False if raw in _FALSE else default


def active_flags(env: Mapping[str, str] | None = None) -> dict[str, bool]:
    active = {name: flag(name, env) for name in DEFAULTS}
    for name in SAFETY_FLAGS:
        if not active[name]:
            log.warning("флаг %s выключен: действует прежнее поведение (@1) без проверок v2", name)
    return active
