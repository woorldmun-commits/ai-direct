"""Evidence Bundle (§96 ТЗ): единственный вход агента. Хеш — sha256 канонического JSON, считается один раз.

Канон: ключи отсортированы; Decimal → {"$dec": "<без хвостовых нулей>"} (1.0 и 1.00 равны, Decimal(1) != "1");
date → {"$date": ISO}, datetime → {"$datetime": ISO}; float запрещён; строки обязаны кодироваться в UTF-8.
facts/findings/metrics/constraints — множества: порядок добавления на хеш не влияет.
Пакет неизменяем: вложенные dict/list заменяются на MappingProxyType/tuple при создании.

Приватность: пакет несёт только обезличенные агрегаты. Ключи из чёрного списка (name, *_name, query, login, token,
email, phone, password, secret, oauth*, api_key, address) на любой глубине отвергаются. Это страховка от ошибок
сборки, а не анонимизатор — полноценная обезличка (значений тоже) — задача PR-4."""

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from app.intelligence.contracts._validate import freeze

_DENIED = ("name", "query", "search_query", "login", "token", "email", "phone", "password", "secret", "api_key",
           "address")


def _check_key(key: Any) -> None:
    if not isinstance(key, str):
        raise ValueError("ключи канонического JSON — строки")
    _utf8(key)
    low = key.lower()
    if low.startswith("$"):
        raise ValueError("ключ не может начинаться с '$': префикс зарезервирован для типизированных значений")
    if low.startswith("oauth") or any(low == w or low.endswith("_" + w) for w in _DENIED):
        raise ValueError(f"privacy: ключ {key!r} запрещён в Evidence Bundle (только обезличенные агрегаты)")


def _utf8(text: str) -> None:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("строка не кодируется в utf-8 (одиночный суррогат)") from None


def _decimal(d: Decimal) -> str:
    if not d.is_finite():
        raise ValueError(f"Decimal не конечен: {d}")
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _plain(x: Any) -> Any:
    if x is None or isinstance(x, (bool, int)):
        return x
    if isinstance(x, str):
        _utf8(x)
        return x
    if isinstance(x, float):
        raise ValueError("float запрещён в каноническом JSON: деньги и доли — Decimal")
    if isinstance(x, Decimal):
        return {"$dec": _decimal(x)}
    if isinstance(x, datetime):  # раньше date: datetime — её подкласс
        return {"$datetime": x.isoformat()}
    if isinstance(x, date):
        return {"$date": x.isoformat()}
    if isinstance(x, Enum):
        return _plain(x.value)
    if isinstance(x, Mapping):
        for k in x:
            _check_key(k)
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (tuple, list)):
        return [_plain(v) for v in x]
    raise ValueError(f"тип {type(x).__name__} не входит в канонический JSON")


def canonical_json(obj: Any) -> str:
    return json.dumps(_plain(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


_SETS = ("facts", "findings", "metrics", "constraints")
_MAPS = ("data_health", "capabilities", "period", "source_registry")


@dataclass(frozen=True)
class EvidenceBundle:
    facts: tuple
    findings: tuple
    metrics: tuple
    constraints: tuple
    data_health: Mapping
    capabilities: Mapping
    period: Mapping
    source_registry: Mapping

    def __post_init__(self):
        for name in _SETS:
            object.__setattr__(self, name, freeze(tuple(getattr(self, name))))
        for name in _MAPS:
            object.__setattr__(self, name, freeze(dict(getattr(self, name))))
        payload = {name: sorted(getattr(self, name), key=canonical_json) for name in _SETS}
        payload.update({name: getattr(self, name) for name in _MAPS})
        canon = canonical_json(payload)  # float, privacy-ключи и не-utf-8 отвергаются здесь
        object.__setattr__(self, "_bundle_hash", hashlib.sha256(canon.encode("utf-8")).hexdigest())

    @property
    def bundle_hash(self) -> str:
        return self._bundle_hash
