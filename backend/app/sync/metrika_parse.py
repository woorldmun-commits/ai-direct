"""Сырой JSON Метрики → строки site_goal. Строже Директа: ответ сверяется с эхом запроса (query), сэмплированный
отчёт отвергается, интервалы обязаны покрыть период день в день. Из ответа берутся только id цели, день и число
достижений — названия целей и всё прочее не сохраняются."""

import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.sources.metrika import MetrikaReportSpec
from app.sync.parse import FormatError, ReportFormatError


@dataclass(frozen=True)
class GoalRow:
    """Всё, что из Метрики попадает в снимок: stat_rows(source=yandex_metrika, level=site_goal, object_id=goal_id)."""
    goal_id: int
    date: date
    conversions: Decimal


def _json(text: str) -> dict:
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        raise ReportFormatError(FormatError.INVALID_JSON, "ответ Метрики не JSON") from None
    if not isinstance(doc, dict):
        raise ReportFormatError(FormatError.INVALID_JSON, "ожидается объект")
    return doc


def parse_goals(text: str) -> frozenset[int]:
    goals = _json(text).get("goals")
    if not isinstance(goals, list):
        raise ReportFormatError(FormatError.MISSING_REQUIRED_COLUMN, "goals")
    ids = [g.get("id") if isinstance(g, dict) else None for g in goals]
    if not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise ReportFormatError(FormatError.INVALID_NUMERIC_VALUE, "goals[].id")
    return frozenset(ids)


def _check_query(doc: dict, spec: MetrikaReportSpec) -> None:
    """Ответ должен быть ответом на наш запрос: счётчик, метрики, период, группировка."""
    q = doc.get("query")
    if not isinstance(q, dict):
        raise ReportFormatError(FormatError.MISSING_REQUIRED_COLUMN, "query")
    expected = {"ids": [spec.counter_id], "metrics": list(spec.metrics), "dimensions": list(spec.dimensions),
                "date1": spec.date_from.isoformat(), "date2": spec.date_to.isoformat(), "group": spec.group}
    if diff := sorted(k for k, v in expected.items() if q.get(k) != v):
        raise ReportFormatError(FormatError.QUERY_MISMATCH, f"query: {diff}")
    if doc.get("sampled") is not False:
        raise ReportFormatError(FormatError.SAMPLED_REPORT, "сэмплированный или без признака sampled")


def _intervals(doc: dict, spec: MetrikaReportSpec) -> list[date]:
    days = (spec.date_to - spec.date_from).days + 1
    expected = [[(spec.date_from + timedelta(i)).isoformat()] * 2 for i in range(days)]
    got = doc.get("time_intervals")
    if not isinstance(got, list):
        raise ReportFormatError(FormatError.MISSING_REQUIRED_COLUMN, "time_intervals")
    if got != expected:
        code = FormatError.TRUNCATED_ROW if len(got) < days else FormatError.DATE_OUT_OF_RANGE
        raise ReportFormatError(code, f"time_intervals: {len(got)} вместо {days} дневных интервалов")
    return [spec.date_from + timedelta(i) for i in range(days)]


def _value(raw, metric: str) -> Decimal:
    if raw is None:
        raise ReportFormatError(FormatError.MISSING_REQUIRED_VALUE, metric)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ReportFormatError(FormatError.INVALID_NUMERIC_VALUE, f"{metric}={raw!r}")
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        raise ReportFormatError(FormatError.INVALID_NUMERIC_VALUE, f"{metric}={raw!r}") from None
    if not value.is_finite():
        raise ReportFormatError(FormatError.INVALID_NUMERIC_VALUE, f"{metric}={raw!r}")
    if value < 0:
        raise ReportFormatError(FormatError.NEGATIVE_VALUE, f"{metric}={raw!r}")
    return value


def parse_bytime(text: str, spec: MetrikaReportSpec, goal_ids: tuple[int, ...]) -> tuple[GoalRow, ...]:
    doc = _json(text)
    _check_query(doc, spec)
    days = _intervals(doc, spec)
    data = doc.get("data")
    if not isinstance(data, list) or len(data) > 1:
        raise ReportFormatError(FormatError.MISSING_REQUIRED_COLUMN, "data: ожидается 0 или 1 строка без dimensions")
    if not data:  # визитов за период не было: это ноль конверсий, а не ошибка API
        return tuple(GoalRow(g, d, Decimal(0)) for g in goal_ids for d in days)
    series = data[0].get("metrics") if isinstance(data[0], dict) else None
    if not isinstance(series, list) or len(series) != len(spec.metrics):
        raise ReportFormatError(FormatError.MISSING_REQUIRED_COLUMN, f"data[0].metrics: нужно {len(spec.metrics)}")
    rows = []
    for goal_id, metric, values in zip(goal_ids, spec.metrics, series):
        if not isinstance(values, list) or len(values) != len(days):
            raise ReportFormatError(FormatError.TRUNCATED_ROW, f"{metric}: значений не столько, сколько дней")
        rows.extend(GoalRow(goal_id, d, _value(v, metric)) for d, v in zip(days, values))
    return tuple(rows)
