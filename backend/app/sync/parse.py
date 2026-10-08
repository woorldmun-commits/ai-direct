"""Сырой TSV Reports API → нормализованные строки. Allowlist: сохраняются только поля StatRow; столбец, которого
не запрашивали, или пропавший столбец — ошибка формата, а не молчаливое расширение снимка."""

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from datetime import date
from decimal import Decimal

from app.sources.conversion import ConversionDefinition
from app.sources.direct import ReportSpec
from app.sync.sanitize import MASK, sanitize, sanitize_placement

# Reports API показывает отсутствующее значение как "--". Смысл зависит от столбца:
#   Conversions_*            "--" → 0: за день по цели конверсий не было;
#   Impressions/Clicks/Cost  "--" → ошибка формата: базовая метрика строки не может отсутствовать,
#                            а 0 выдал бы непроверенное значение за факт.
# Производные метрики (CostPerConversion и т. п.) не запрашиваем: CPA считает правило, и при 0 конверсий
# его нет вовсе (NO_CONVERSIONS), а не «CPA = 0».
EMPTY = "--"


class FormatError(str, Enum):
    """Структурированный код ошибки формата: по нему, а не по тексту, решается, что делать дальше."""
    EMPTY_REPORT = "empty_report"
    UNEXPECTED_COLUMN = "unexpected_column"
    MISSING_REQUIRED_COLUMN = "missing_required_column"
    COLUMN_ORDER_CHANGED = "column_order_changed"
    TRUNCATED_ROW = "truncated_row"
    EXTRA_CELLS = "extra_cells"
    INVALID_DATE = "invalid_date"
    DATE_OUT_OF_RANGE = "date_out_of_range"
    MISSING_REQUIRED_VALUE = "missing_required_value"  # "--" там, где значение обязательно
    INVALID_NUMERIC_VALUE = "invalid_numeric_value"
    NEGATIVE_VALUE = "negative_value"
    INVALID_JSON = "invalid_json"
    QUERY_MISMATCH = "query_mismatch"   # Метрика ответила не на тот запрос (счётчик, метрики, период)
    SAMPLED_REPORT = "sampled_report"   # Метрика отдала сэмплированные данные
    UNEXPECTED_VALUE = "unexpected_value"  # значение вне фильтра запроса (AdNetworkType не AD_NETWORK)


class ReportFormatError(ValueError):
    """В sync_runs: error_code = invalid_report_format, причина — code. detail — только для лога."""

    def __init__(self, code: FormatError, detail: str):
        super().__init__(f"{code.value}: {detail}")
        self.code, self.detail = code, detail


@dataclass(frozen=True)
class StatRow:
    """Всё, что из Директа попадает в снимок. Новое поле = осознанное изменение allowlist (тест это требует)."""
    level: str
    campaign_id: int
    date: date
    impressions: int
    clicks: int
    cost: Decimal
    conversions: Decimal | None  # данные Метрики по цели в отчёте Директа; None — цели не выбраны
    query: str | None = None     # только level = query, уже санитизирован

    def key(self) -> tuple:
        return (self.level, self.campaign_id, self.query, self.date)


@dataclass(frozen=True)
class PlacementRow(StatRow):
    """Строка уровня placement: площадка сетей внутри кампании. Отдельный класс, а не поле StatRow, — allowlist
    площадок заморожен своим тестом (tests/test_placements_sync.py). AdNetworkType не хранится: это проверка
    фильтра отчёта, а все строки здесь — сети."""
    placement: str = MASK  # нормализованный домен/приложение (sanitize_placement); MASK — имя не прошло allowlist

    def key(self) -> tuple:
        return (self.level, self.campaign_id, self.placement, self.date)


def placement_id(name: str) -> int:
    """object_id площадки в stat_rows: у площадки в Reports API нет числового ID — стабильный 63-битный хэш
    нормализованного имени (одинаковый во всех снимках и workspace; имя — не ПД). Коллизия при 2^63 —
    пренебрежимо; она упёрлась бы в уникальный индекс stat_rows_grain, а не смешала бы данные молча."""
    return int.from_bytes(hashlib.sha256(f"placement:{name}".encode()).digest()[:8], "big") >> 1


def query_hash(sanitized: str) -> bytes:
    """Ключ дедупликации текстов запроса — от санитизированного текста: хэш сырого телефона перебирается."""
    return hashlib.sha256(sanitized.encode()).digest()


def _required(raw: str, column: str) -> str:
    if raw == EMPTY:
        raise ReportFormatError(FormatError.MISSING_REQUIRED_VALUE, column)
    return raw


_INT = re.compile(r"[0-9]{1,18}")            # ASCII-цифры: str.isdigit() пропускает «²» и «١٢»
_MONEY = re.compile(r"[0-9]{1,12}(\.[0-9]{1,6})?")  # в пределах numeric(14,2); без «1E+2», «1_000», пробелов
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")    # fromisoformat в 3.11 принимает и «20260101»


def _count(raw: str, column: str) -> int:
    if not _INT.fullmatch(_required(raw, column)):
        raise ReportFormatError(FormatError.INVALID_NUMERIC_VALUE, f"{column}={raw!r}")
    return int(raw)


def _money(raw: str, column: str) -> Decimal:
    """returnMoneyInMicros: false → рубли с двумя знаками, сразу в Decimal (без float до конца расчёта)."""
    if _required(raw, column).startswith("-") and _MONEY.fullmatch(raw[1:]):
        raise ReportFormatError(FormatError.NEGATIVE_VALUE, f"{column}={raw!r}")
    if not _MONEY.fullmatch(raw):
        raise ReportFormatError(FormatError.INVALID_NUMERIC_VALUE, f"{column}={raw!r}")
    return Decimal(raw)


def _row(values: dict[str, str], spec: ReportSpec, conv_columns: tuple[str, ...],
         date_from: date, date_to: date) -> StatRow:
    try:
        if not _DATE.fullmatch(_required(values["Date"], "Date")):
            raise ValueError
        day = date.fromisoformat(values["Date"])
    except ValueError:
        raise ReportFormatError(FormatError.INVALID_DATE, f"Date={values['Date']!r}") from None
    if not date_from <= day <= date_to:
        raise ReportFormatError(FormatError.DATE_OUT_OF_RANGE, f"Date {day} вне {date_from}–{date_to}")
    campaign_id = _count(values["CampaignId"], "CampaignId")
    # "--" в столбце конверсий = 0 конверсий — решение владельца, см. empty_cell_semantics у conversions в
    # app/intelligence/metrics/definitions.py (там же его тест).
    conversions = (sum((Decimal(0) if values[c] == EMPTY else _money(values[c], c) for c in conv_columns),
                       Decimal(0)) if conv_columns else None)
    common = dict(
        level=spec.level, campaign_id=campaign_id, date=day,
        impressions=_count(values["Impressions"], "Impressions"), clicks=_count(values["Clicks"], "Clicks"),
        cost=_money(values["Cost"], "Cost"), conversions=conversions,
    )
    if "Placement" in values:
        # фильтр отчёта — «только сети»; строка поиска значит, что фильтр не применился: ошибка, а не данные
        if values.get("AdNetworkType") != "AD_NETWORK":
            raise ReportFormatError(FormatError.UNEXPECTED_VALUE, f"AdNetworkType={values.get('AdNetworkType')!r}")
        return PlacementRow(**common, placement=sanitize_placement(values["Placement"]))
    return StatRow(**common, query=sanitize(values["Query"]) if "Query" in values else None)


def parse_report(text: str, spec: ReportSpec, conversions: ConversionDefinition | None,
                 date_from: date, date_to: date) -> tuple[StatRow, ...]:
    # только "\n": splitlines() режет строку и по U+2028, \x85 и т. п. внутри текста запроса
    lines = [line.rstrip("\r") for line in text.split("\n") if line.strip()]
    if not lines:
        raise ReportFormatError(FormatError.EMPTY_REPORT, "нет строки столбцов")
    conv_columns = conversions.direct_columns() if conversions else ()
    expected = spec.fields + conv_columns
    header = tuple(lines[0].split("\t"))
    if extra := sorted(set(header) - set(expected)):
        raise ReportFormatError(FormatError.UNEXPECTED_COLUMN, f"лишние {extra}")
    if missing := sorted(set(expected) - set(header)):
        raise ReportFormatError(FormatError.MISSING_REQUIRED_COLUMN, f"нет {missing}")
    if header != expected:
        raise ReportFormatError(FormatError.COLUMN_ORDER_CHANGED, str(header))
    rows = []
    for n, line in enumerate(lines[1:], start=2):
        cells = line.split("\t")
        if len(cells) != len(header):
            code = FormatError.TRUNCATED_ROW if len(cells) < len(header) else FormatError.EXTRA_CELLS
            raise ReportFormatError(code, f"строка {n}: {len(cells)} значений вместо {len(header)}")
        rows.append(_row(dict(zip(header, cells)), spec, conv_columns, date_from, date_to))
    return tuple(rows)
