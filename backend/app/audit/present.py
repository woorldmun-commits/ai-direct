"""Как вывод показывается человеку: действие, согласованное с уровнем политики, и заголовок карточки
(API_CONTRACT.md §5). Чистые функции без БД и LLM; числа — только из сохранённого вывода.

Действие ≠ кандидат. Правило предлагает кандидата (findings.action, остаётся в БД неизменным), политика назначает
уровень (findings.action_level). Человеку отдаётся действие этого уровня:
- inspect_only → «проверить»: {type: investigate, topic: <семейство>, checks, suggest, placements, execution}, без
  ставки и без исключения площадок — даже если кандидат был «снизить ставку» или «исключить площадки»;
- review / change и decrease_bid при неизвестной (или не ручной) стратегии кампании → не «только ставка», а рычаги
  по стратегии: ручные ставки → снизить ставку на N%; автостратегия → снизить целевую цену конверсии / проверить цели
  (SnapshotView стратегию не знает — в v1.0 она всегда unknown);
- decrease_bid при известной ручной стратегии и уровне change → {type: decrease_bid, change_pct};
- exclude_placements на review → {type: exclude_placements, placements_count, placements}.
Неизвестная форма → ValueError: вызывающий решает, что показать вместо неё (API — action = null)."""

from decimal import Decimal

from app.audit.templates import _rub

CENT = Decimal("0.01")
EXECUTION = "manual"  # v1.0 не изменяет кабинеты: всё, что предлагается, человек делает сам
SUGGESTIONS = ("set_target_cpa",)
STRATEGIES = ("unknown", "manual", "auto")

# Что проверить по семейству (закрытый список кодов; тексты — словарь фронтенда).
CHECKS = ("conversion_goals", "strategy", "search_queries_negative_keywords", "network_placements")
CHECKS_BY_TOPIC = {
    "zero_conv_campaign": ("conversion_goals", "strategy", "search_queries_negative_keywords"),
    "high_cpa": ("conversion_goals", "strategy", "search_queries_negative_keywords", "network_placements"),
    "zero_conv_placements": ("network_placements",),
}
DEFAULT_CHECKS = ("conversion_goals", "strategy")
# Рычаги снижения CPA по стратегии кампании (decrease_bid, когда ручная ставка может быть недоступна).
LEVERS = ("decrease_bid", "lower_target_cpa", "check_conversion_goals")


def _pct(raw) -> str:
    pct = Decimal(str(raw))
    if not pct < 0:
        raise ValueError("decrease_bid: change_pct < 0")
    return format(pct.quantize(CENT), "f")


def _suggest(raw: dict) -> str | None:
    s = raw.get("suggest")
    if s is not None and s not in SUGGESTIONS:
        raise ValueError(f"action.suggest: {s!r} вне контракта")
    return s


def _placements(raw: dict, meta: dict) -> list[dict]:
    """Имя — нормализованный домен или id приложения (sync/sanitize.py), не ПД: человек ищет площадку по нему в
    Директе. Нет имени (маска, нет справочника) — null."""
    ids = [int(pid) for pid in raw["placement_ids"]]
    if not ids or raw.get("execution", EXECUTION) != EXECUTION:
        raise ValueError("exclude_placements: нужны площадки, исполнение только ручное")
    return [{"id": str(pid), "name": meta.get(f"placement_{pid}_name")} for pid in ids]


def _checks(topic: str, raw: dict) -> list[str]:
    checks = list(raw.get("check") or CHECKS_BY_TOPIC.get(topic, DEFAULT_CHECKS))
    if not checks or any(c not in CHECKS for c in checks):
        raise ValueError(f"investigate: checks вне контракта: {checks!r}")
    return checks


def investigate(topic: str, raw: dict, meta: dict) -> dict:
    """Форма «проверить»: что посмотреть самому, без изменения настроек."""
    placements = _placements(raw, meta) if raw.get("type") == "exclude_placements" else None
    return {"type": "investigate", "topic": topic, "checks": _checks(topic, raw), "suggest": _suggest(raw),
            "placements": placements, "execution": EXECUTION}


def lower_cpa(change_pct: str, strategy: str) -> dict:
    """Рычаги снижения CPA по стратегии: какие из них применимы, решает человек, видя стратегию в Директе."""
    levers = []
    if strategy in ("unknown", "manual"):
        levers.append({"strategy": "manual", "lever": "decrease_bid", "change_pct": change_pct})
    if strategy in ("unknown", "auto"):
        levers += [{"strategy": "auto", "lever": "lower_target_cpa", "change_pct": None},
                   {"strategy": "auto", "lever": "check_conversion_goals", "change_pct": None}]
    return {"type": "lower_cpa", "strategy": strategy, "levers": levers, "execution": EXECUTION}


def present_action(raw: dict, level: str, topic: str, meta: dict, strategy: str = "unknown") -> dict:
    """Кандидат правила + уровень политики → действие для человека (одна из форм API_CONTRACT §5)."""
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy {strategy!r}")
    kind = raw.get("type")
    if kind not in ("decrease_bid", "investigate_zero_conversions", "investigate_cpa_growth", "exclude_placements"):
        raise ValueError(f"action.type {kind!r} вне контракта v1.0")
    if level == "inspect_only":
        if kind == "decrease_bid":
            _pct(raw["change_pct"])  # кандидат обязан быть корректным, даже если показывается «проверить»
        return investigate(topic, raw, meta)
    if level not in ("review", "change"):
        raise ValueError(f"action_level {level!r}")
    if kind == "decrease_bid":
        pct = _pct(raw["change_pct"])
        if strategy == "manual" and level == "change":
            return {"type": "decrease_bid", "change_pct": pct, "execution": EXECUTION}
        return lower_cpa(pct, strategy)
    if kind == "exclude_placements":
        placements = _placements(raw, meta)
        return {"type": "exclude_placements", "placements_count": len(placements), "placements": placements,
                "execution": EXECUTION}
    return investigate(topic, raw, meta)  # «проверить» кандидата выше inspect_only не бывает — та же форма


def _object(object_type: str, object_id: int, name: str | None) -> str:
    label = {"campaign": "кампания", "account": "кабинет", "placement": "площадка"}.get(object_type, object_type)
    return f"{label} «{name}»" if name else f"{label} {object_id}"


def _num(meta: dict, key: str) -> str | None:
    raw = meta.get(key)
    try:
        return _rub(Decimal(str(raw))) if raw is not None else None
    except ArithmeticError:
        return None


def title(topic: str, object_type: str, object_id: int, meta: dict, name: str | None = None,
          insufficient: bool = False) -> str:
    """Заголовок карточки: семейство + объект + ключевая цифра из вывода (meta.actual / reference). Без LLM.
    insufficient — последний аудит не смог проверить проблему: старую цифру не показываем."""
    obj = _object(object_type, object_id, name)
    actual, reference = _num(meta, "actual"), _num(meta, "reference")
    if insufficient:
        head = {"high_cpa": "Высокий CPA", "zero_conv_campaign": "Расход без конверсий",
                "zero_conv_placements": "Площадки РСЯ без конверсий"}.get(topic, topic)
        return f"{head} · {obj} · недостаточно данных для проверки"
    if topic == "high_cpa" and actual and reference:
        ref = "целевого" if meta.get("reference_type") == "target" else "обычного"
        return f"CPA {actual} ₽ выше {ref} {reference} ₽ · {obj}"
    if topic == "zero_conv_campaign" and actual:
        return f"Расход {actual} ₽ без конверсий · {obj}"
    if topic == "zero_conv_placements" and actual:
        count = len([i for i in str(meta.get("placement_ids", "")).split(",") if i])
        return f"Площадки РСЯ без конверсий ({count}): {actual} ₽ · {obj}"
    return f"{topic} · {obj}"
