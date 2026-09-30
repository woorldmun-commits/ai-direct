"""Замороженное определение конверсии (PRD §4.1 «Одинаковое определение конверсии»).

Конверсии по кампаниям для CPA берутся из отчёта Директа (Conversions_<цель>_<модель>), но это данные Метрики:
Директ лишь возвращает их в одном отчёте с расходом. Метрика отдельно даёт site_goal — для здоровья и сверки.
Одно и то же определение уходит в оба запроса и сохраняется в снимке: старый аудит не начнёт использовать
новую цель клиента или другую атрибуцию."""

from dataclasses import dataclass

# Каноничные имена — как в Метрике; Директ называет те же модели своими кодами.
ATTRIBUTION_DIRECT_CODE = {
    "lastsign": "LSC",                   # последний значимый переход
    "last": "LC",                        # последний переход
    "first": "FC",                       # первый переход
    "last_yandex_direct_click": "LYDC",  # последний переход из Директа
}
MAX_GOALS = 10  # предел параметра Goals в Reports API Директа


@dataclass(frozen=True)
class ConversionDefinition:
    counter_id: int
    goal_ids: tuple[int, ...]
    attribution: str = "lastsign"

    def __post_init__(self):
        if not self.goal_ids or len(self.goal_ids) > MAX_GOALS:
            raise ValueError(f"goal_ids: от 1 до {MAX_GOALS} целей")
        if tuple(sorted(set(self.goal_ids))) != self.goal_ids:
            raise ValueError("goal_ids: по возрастанию, без повторов — иначе одно определение выглядит как два")
        if self.attribution not in ATTRIBUTION_DIRECT_CODE:
            raise ValueError(f"attribution: одно из {sorted(ATTRIBUTION_DIRECT_CODE)}")

    def direct_columns(self) -> tuple[str, ...]:
        code = ATTRIBUTION_DIRECT_CODE[self.attribution]
        return tuple(f"Conversions_{g}_{code}" for g in self.goal_ids)

    def to_json(self) -> dict:
        """Хранится в snapshots.conversion_definition и в замороженных настройках аудита."""
        return {"provider": "yandex_metrika", "counter_id": self.counter_id, "goal_ids": list(self.goal_ids),
                "attribution": self.attribution}

    @classmethod
    def from_json(cls, d: dict) -> "ConversionDefinition":
        return cls(d["counter_id"], tuple(d["goal_ids"]), d["attribution"])
