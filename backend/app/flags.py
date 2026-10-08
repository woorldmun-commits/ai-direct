"""Флаги функций — единственное место, где читаются их переменные окружения (имя флага в верхнем регистре:
INTELLIGENCE_V2, LLM_ENABLED …). Умолчания — решения владельца продукта (Intelligence 2.0). Пустое или непонятное
значение оставляет умолчание: опечатка не включает и не выключает функцию."""

import logging
import os
from typing import Mapping

log = logging.getLogger(__name__)

DEFAULTS: Mapping[str, bool] = {
    "intelligence_v2": True,
    "source_of_truth_v2": True,   # правила @2: источник конверсий и CPA — из реестра метрик
    "evidence_bundle_v2": True,
    "safety_engine_v2": True,     # safety_policy@2
    "capability_registry_v2": True,
    "chief_analyst": False,
    "search_intelligence": False,
    "rsya_intelligence": False,
    "root_cause": False,
    "opportunity_engine": False,
    "creative_intelligence": False,
    "llm_enabled": False,
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
