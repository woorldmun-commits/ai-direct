"""Замороженное определение конверсии (PRD §4.1 «Одинаковое определение конверсии»).

Конверсии по кампаниям для CPA берутся из отчёта Директа (Conversions_<цель>_<модель>), но это данные Метрики:
Директ лишь возвращает их в одном отчёте с расходом. Метрика отдельно даёт site_goal — для здоровья и сверки.
Одно и то же определение уходит в оба запроса и сохраняется в снимке: старый аудит не начнёт использовать
новую цель клиента или другую атрибуцию."""

from dataclasses import dataclass

# Каноничные имена — как в API Метрики; Директ называет те же модели своими кодами. Только модели, которые API
# считают сами: устаревшие (lastsign/LSC, first/FC, last_yandex_direct_click/LYDC) Яндекс молча подменяет
# ближайшими (с 25.06.2026 в Метрике; Директ — с предупреждением), и снимок записал бы не ту модель, по которой
# посчитаны конверсии.
ATTRIBUTION_DIRECT_CODE = {
    "cross_device_last_significant": "LSCCD",  # последний значимый переход, все устройства
    "last": "LC",                              # последний переход
    "cross_device_first": "FCCD",              # первый переход, все устройства
    "automatic": "AUTO",                       # автоматическая атрибуция
}
MAX_GOALS = 10  # предел параметра Goals в Reports API Директа


@dataclass(frozen=True)
class ConversionDefinition:
    counter_id: int
    goal_ids: tuple[int, ...]
    attribution: str = "cross_device_last_significant"

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
