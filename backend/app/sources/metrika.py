"""Источник Яндекс Метрики: Reports API (агрегаты по дням, /stat/v1/data/bytime) и список целей счётчика
(management API). Logs API не используем: неагрегированные визиты снимку не нужны.

Метрика — диагностический источник: здоровье счётчика и целей, сверка с конверсиями из отчёта Директа.
Норматив CPA — отчёт Директа (sources/conversion.py). Источник отдаёт сырой JSON; разбор — sync/metrika_parse.py.
Реализации: MetrikaFixture (тесты) и MetrikaApi (api-metrika.yandex.net, только чтение)."""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Protocol

import httpx

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


# --- API ------------------------------------------------------------------------------------------------------

API_URL = "https://api-metrika.yandex.net"
# HTTP-статус → код источника. Токен — тот же API-приложения, что у Директа (права metrika:read).
_STATUS_CODES = {400: "invalid_request", 401: "access_denied", 403: "access_denied", 404: "counter_not_found"}


@dataclass(frozen=True)
class MetrikaApi:
    """Management API (счётчики, цели) и Reporting API (/stat/v1/data/bytime) — только чтение, сырой JSON.
    Ошибки → MetrikaUnavailable с кодом; сеть, 429 и 5xx — report_unavailable (повторит следующая синхронизация)."""
    http: httpx.Client
    access_token: str = field(repr=False)

    def _get(self, path: str, params: dict, counter_id: int) -> str:
        try:
            r = self.http.get(f"{API_URL}{path}", params=params, timeout=60,
                              headers={"Authorization": f"OAuth {self.access_token}"})
        except httpx.TransportError:
            raise MetrikaUnavailable(counter_id, "report_unavailable") from None
        if r.status_code == 200:
            return r.text
        raise MetrikaUnavailable(counter_id, _STATUS_CODES.get(r.status_code, "report_unavailable"))

    def fetch_goals(self, counter_id: int) -> str:
        return self._get(f"/management/v1/counter/{counter_id}/goals", {}, counter_id)

    def fetch_bytime(self, spec: MetrikaReportSpec) -> str:
        return self._get("/stat/v1/data/bytime", {k: v for k, v in spec.params().items() if v}, spec.counter_id)

    def fetch_counters(self) -> str:
        """Счётчики, доступные токену, — для онбординга (sources/metrika_discovery.py)."""
        return self._get("/management/v1/counters", {"per_page": "1000", "status": "Active"}, 0)
