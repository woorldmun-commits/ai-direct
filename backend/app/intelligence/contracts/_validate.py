"""Общие проверки полей контрактов: идентификаторы и текст. Всё, что попадёт в промпт или журнал, проходит их."""

import re
import unicodedata
from types import MappingProxyType
from typing import Any, Mapping

_IDENT = re.compile(r"[A-Za-z0-9_.:@-]{1,128}")  # '@' — для версий вида cpa@1
MAX_TEXT = 2000


def check_ident(name: str, value: Any) -> None:
    if not isinstance(value, str) or not _IDENT.fullmatch(value):
        raise ValueError(f"{name}: ожидается идентификатор [A-Za-z0-9_.:@-]{{1,128}}")


def check_ident_tuple(name: str, values: Any) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{name}: ожидается tuple")
    for v in values:
        check_ident(name, v)


def check_text(name: str, value: Any) -> None:
    """Непустой текст до 2000 символов без управляющих символов (в том числе переводов строк и табуляции)."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}: пусто или не строка")
    if len(value) > MAX_TEXT:
        raise ValueError(f"{name}: длиннее {MAX_TEXT} символов")
    if any(unicodedata.category(ch) in ("Cc", "Zl", "Zp") for ch in value):
        raise ValueError(f"{name}: управляющие символы запрещены")


def check_text_tuple(name: str, values: Any) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{name}: ожидается tuple")
    for v in values:
        check_text(name, v)


def freeze(x: Any) -> Any:
    """Рекурсивно: Mapping → MappingProxyType (копия), list/tuple → tuple. Остальное не трогает."""
    if isinstance(x, Mapping):
        return MappingProxyType({k: freeze(v) for k, v in x.items()})
    if isinstance(x, (list, tuple)):
        return tuple(freeze(v) for v in x)
    return x
