"""Источник Яндекс Метрики: Reports API (агрегаты по дням, /stat/v1/data/bytime) и список целей счётчика
(management API). Logs API не используем: неагрегированные визиты снимку не нужны.

Метрика — диагностический источник: здоровье счётчика и целей, сверка с конверсиями из отчёта Директа.
Норматив CPA — отчёт Директа (sources/conversion.py). Источник отдаёт сырой JSON; разбор — sync/metrika_parse.py.
Реализации: MetrikaFixture. MetrikaApi — вместе с DirectApi, когда будет доступ."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from app.sources.conversion import ConversionDefinition

# Ошибки уровня API: синхронизация Метрики не удалась. Недостаток данных (0 конверсий) — не ошибка.
ERROR_CODES = frozenset({"access_denied", "counter_not_found", "goal_not_found", "invalid_request",
                         "report_unavailable"})


@dataclass(frozen=True)
class MetrikaReportSpec:
    """Запрос к Reports API целиком. Ограничения API: ≤ 20 metrics, ≤ 10 dimensions, ≤ 100 000 строк —
    здесь 0 dimensions, ≤ 10 metrics (по цели на метрику), 37 интервалов."""
    counter_id: int
    date_from: date
    date_to: date
    metrics: tuple[str, ...]
    attribution: str
    dimensions: tuple[str, ...] = ()  # весь сайт: цели не делятся по кампаниям
    group: str = "day"
    accuracy: str = "full"           # без сэмплирования

    @classmethod
    def for_definition(cls, d: ConversionDefinition, date_from: date, date_to: date) -> "MetrikaReportSpec":
        return cls(d.counter_id, date_from, date_to, tuple(f"ym:s:goal{g}reaches" for g in d.goal_ids), d.attribution)

    def params(self) -> dict[str, str]:
        return {"ids": str(self.counter_id), "metrics": ",".join(self.metrics), "dimensions": ",".join(self.dimensions),
                "date1": self.date_from.isoformat(), "date2": self.date_to.isoformat(), "group": self.group,
                "attribution": self.attribution, "accuracy": self.accuracy}


class MetrikaUnavailable(Exception):
    def __init__(self, counter_id: int, error_code: str):
        assert error_code in ERROR_CODES, error_code
        super().__init__(f"counter {counter_id}: {error_code}")
        self.counter_id, self.error_code = counter_id, error_code


class MetrikaSource(Protocol):
    def fetch_goals(self, counter_id: int) -> str: ...
    def fetch_bytime(self, spec: MetrikaReportSpec) -> str: ...


class MetrikaFixture:
    """<root>/<counter_id>/goals.json и bytime.json; <root>/<counter_id>/unavailable — код ошибки API.
    Каталога счётчика нет — counter_not_found."""

    def __init__(self, root: Path):
        self.root = root

    def _counter(self, counter_id: int) -> Path:
        d = self.root / str(counter_id)
        if not d.exists():
            raise MetrikaUnavailable(counter_id, "counter_not_found")
        if (d / "unavailable").exists():
            raise MetrikaUnavailable(counter_id, (d / "unavailable").read_text(encoding="utf-8").strip())
        return d

    def fetch_goals(self, counter_id: int) -> str:
        return (self._counter(counter_id) / "goals.json").read_text(encoding="utf-8")

    def fetch_bytime(self, spec: MetrikaReportSpec) -> str:
        return (self._counter(spec.counter_id) / "bytime.json").read_text(encoding="utf-8")
