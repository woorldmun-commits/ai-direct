"""Privacy Guard: промпт-пакет для LLM из Evidence Bundle (ARCHITECTURE.md §2.4, AI_GOVERNANCE.md §2.4).

Только allowlist: поля вне списка отбрасываются, ключи из чёрного списка на любой глубине — PrivacyError.
Строковые значения — только слаги ([a-z], цифры, «_», сегменты через «:» или «@»): так в пакет не проходят
названия кампаний и площадок, тексты запросов, email, телефоны и строки-инъекции — без попытки их распознать.
Объекты заменяются непрозрачными ссылками obj_1… на один запрос; таблица соответствия остаётся на сервере."""

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from app.intelligence.contracts.evidence import EvidenceBundle

_SLUG = re.compile(r"[a-z][a-z0-9_]{0,63}(?:[:@][a-z0-9_]{1,64}){0,4}")
_EVIDENCE_ID = re.compile(r"[a-z][a-z0-9_]{0,31}")
_DENIED = ("name", "title", "text", "query", "keyword", "login", "email", "phone", "token", "secret", "password",
           "address", "url", "comment", "oauth", "api_key")
_NUMERIC = frozenset({"exposure", "from", "to"})
_SLUG_KEYS = frozenset({"id", "kind", "rule", "metric", "action_type", "action_level", "data_sufficiency", "reason",
                        "finding", "level"})
_ITEM_KEYS = _NUMERIC | _SLUG_KEYS | {"object", "values", "reasons"}
OBJECT_REF = re.compile(r"obj_\d+")


class PrivacyError(ValueError):
    """Пакет не собран: в нём было то, что нельзя отправлять в LLM. Сообщение — без значения поля."""


@dataclass(frozen=True)
class Packet:
    payload: Mapping           # уходит в LLM
    refs: Mapping[str, Any]    # obj_N → исходный объект; только на сервере, не сохраняется
    numbers: Mapping[str, frozenset]  # evidence_id → числа факта (для Judge)
    kinds: Mapping[str, str]          # evidence_id → kind


def _check_key(key: Any) -> str:
    if not isinstance(key, str) or not _SLUG.fullmatch(key):
        raise PrivacyError("ключ не слаг")
    if any(word in key for word in _DENIED):
        raise PrivacyError(f"запрещённый ключ {key!r}")
    return key


def _scalar(value: Any) -> Any:
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal) and value.is_finite():
        return format(value, "f")
    if isinstance(value, str) and _SLUG.fullmatch(value):
        return value
    if isinstance(value, (tuple, list)):
        return [_scalar(v) for v in value]
    raise PrivacyError("значение не слаг и не число")


def _numbers(item: Mapping) -> frozenset:
    found = [item[k] for k in _NUMERIC if k in item] + list(item.get("values", {}).values())
    out = set()
    for text in found:
        try:
            d = Decimal(text)
        except (ArithmeticError, TypeError, ValueError):
            continue  # слаг («high»), не число
        if d.is_finite():  # «nan» и «inf» — слаги, а не числа
            out.add(d)
    return frozenset(out)


class _Refs:
    def __init__(self):
        self.by_object: dict = {}

    def ref(self, obj: Any) -> str:
        key = (type(obj).__name__, str(obj))
        if key not in self.by_object:
            self.by_object[key] = (f"obj_{len(self.by_object) + 1}", obj)
        return self.by_object[key][0]

    def table(self) -> Mapping:
        return MappingProxyType({ref: obj for ref, obj in self.by_object.values()})


def clean_item(item: Mapping, refs: _Refs) -> dict:
    out = {}
    for key, value in item.items():
        _check_key(key)
        if key not in _ITEM_KEYS or value is None:
            continue
        if key == "object":
            out[key] = refs.ref(value)
        elif key == "values":
            if not isinstance(value, Mapping):
                raise PrivacyError("values: ожидается словарь")
            out[key] = {_check_key(k): _scalar(v) for k, v in value.items() if not isinstance(v, bool)}
        elif key in _NUMERIC and (isinstance(value, bool) or not isinstance(value, (int, Decimal))):
            raise PrivacyError(f"{key}: ожидается число")
        else:
            out[key] = _scalar(value)
    return out


def _flat(mapping: Mapping) -> dict:
    """capabilities / data_health: значение — слаг, число, флаг или словарь, из которого берётся status."""
    out = {}
    for key, value in mapping.items():
        if isinstance(value, Mapping):
            value = value.get("status")
        out[_check_key(key)] = _scalar(value)
    return out


def build_packet(bundle: EvidenceBundle, plan: tuple[Mapping, ...] = ()) -> Packet:
    refs = _Refs()
    items = [dict(f) for f in bundle.facts] + [{"kind": "finding", **f} for f in bundle.findings]
    facts = []
    for item in sorted(items, key=lambda i: str(i.get("id"))):
        if not isinstance(item.get("id"), str) or not _EVIDENCE_ID.fullmatch(item["id"]):
            raise PrivacyError("факт без корректного id")
        facts.append(clean_item(item, refs))
    ids = [f["id"] for f in facts]
    if len(ids) != len(set(ids)):
        raise PrivacyError("повторяющиеся id фактов")
    payload = {"facts": facts, "capabilities": _flat(bundle.capabilities), "data_health": _flat(bundle.data_health),
               "plan": [clean_item(p, refs) for p in plan]}
    return Packet(payload=payload, refs=refs.table(),
                  numbers=MappingProxyType({f["id"]: _numbers(f) for f in facts}),
                  kinds=MappingProxyType({f["id"]: f.get("kind", "fact") for f in facts}))
