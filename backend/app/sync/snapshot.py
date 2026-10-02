"""Синхронизация одного рекламного аккаунта → самодостаточный 37-дневный снимок (ARCHITECTURE.md §2.6).
Снимок неизменяем; правила читают его только через SnapshotView.

Источники независимы: отчёт Директа (расход + конверсии Метрики по кампаниям) обязателен — без него снимка нет;
Метрика (site_goal) — диагностика: её отказ записывается в снимок (source_failures), снимок всё равно существует."""

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Mapping

from app.rules.domain import DIRECT_CONVERSIONS, HISTORY_DAYS, CampaignDay, PlacementDay, SnapshotView, frozen
from app.sources.conversion import ConversionDefinition
from app.sources.direct import (CAMPAIGN_REPORT, PLACEMENT_REPORT, QUERY_REPORT, AccountUnavailable,
                                ConnectionUnavailable, DirectApiError, DirectSource)
from app.sources.metrika import MetrikaReportSpec, MetrikaSource, MetrikaUnavailable
from app.sync.metrika_parse import GoalRow, parse_bytime, parse_goals
from app.sync.parse import PlacementRow, ReportFormatError, StatRow, parse_report, placement_id

# ponytail: окно дозачёта конверсий Директа — 3 дня по умолчанию; проверить на живых данных (открытый вопрос §12.3).
PARTIAL_DAYS = 3


@dataclass(frozen=True)
class Snapshot:
    login: str
    period_from: date
    period_to: date
    partial_from: date  # даты >= partial_from → data_status = partial
    sources: frozenset[str]  # API-источники, данные которых в снимке: yandex_direct [, yandex_metrika]
    rows: tuple[StatRow, ...]
    conversion_definition: ConversionDefinition | None = None  # None: цели не выбраны, конверсий нет
    goal_rows: tuple[GoalRow, ...] = ()
    source_failures: Mapping[str, str] = field(default_factory=lambda: frozen({}))  # источник → код ошибки API


@dataclass(frozen=True)
class SyncFailure:
    account: str               # client_login Директа или counter:<id> Метрики
    error_code: str            # access_denied · counter_not_found · goal_not_found · invalid_report_format · …
    reason: str | None = None  # для invalid_report_format — FormatError: negative_value, unexpected_column, …
    request_id: str | None = None  # invalid_request: RequestId Яндекса — для обращения в поддержку, не для UI


def _merge(rows: tuple[StatRow, ...]) -> tuple[StatRow, ...]:
    """Строки с одинаковым ключом складываются: после санитизации разные запросы могут совпасть
    («звонок 8 916 …» и «звонок 8 903 …» → «звонок ***»), после нормализации — площадки («www.site.ru» и «site.ru»)."""
    merged: dict[tuple, StatRow] = {}
    for r in rows:
        prev = merged.get(r.key())
        if prev is None:
            merged[r.key()] = r
            continue
        conv = None if r.conversions is None else prev.conversions + r.conversions
        merged[r.key()] = replace(prev, impressions=prev.impressions + r.impressions, clicks=prev.clicks + r.clicks,
                                  cost=prev.cost + r.cost, conversions=conv)
    return tuple(sorted(merged.values(), key=lambda r: (r.level, r.campaign_id, r.date, r.query or "",
                                                        getattr(r, "placement", ""))))


def sync_account(source: DirectSource, login: str, conversions: ConversionDefinition | None,
                 period_to: date, *, placements: bool = False) -> Snapshot | SyncFailure:
    """period_to передаёт вызывающий (вчера по МСК): функция не читает текущее время.
    placements: третий отчёт — площадки РСЯ (PLACEMENT_REPORT). Пока выключен по умолчанию: включается в воркере
    после проверки отчёта на песочнице; его ошибка, как и ошибка отчёта запросов, — отказ всей синхронизации."""
    period_from = period_to - timedelta(HISTORY_DAYS - 1)
    specs = (CAMPAIGN_REPORT, QUERY_REPORT) + ((PLACEMENT_REPORT,) if placements else ())
    try:
        rows = tuple(
            row
            for spec in specs
            for row in parse_report(source.fetch_report(login, spec, conversions, period_from, period_to),
                                    spec, conversions, period_from, period_to)
        )
    except (AccountUnavailable, ConnectionUnavailable) as e:
        return SyncFailure(login, e.error_code)
    except ReportFormatError as e:
        return SyncFailure(login, "invalid_report_format", e.code.value)
    except DirectApiError as e:  # запрос отклонён, повтор не поможет: наша ошибка запроса или ограничение отчёта
        return SyncFailure(login, "invalid_request", request_id=e.request_id)
    return Snapshot(login, period_from, period_to, period_to - timedelta(PARTIAL_DAYS - 1),
                    frozenset({"yandex_direct"}), _merge(rows), conversions)


def sync_accounts(source: DirectSource, logins: tuple[str, ...], conversions: ConversionDefinition | None,
                  period_to: date) -> dict[str, Snapshot | SyncFailure]:
    """Каждый client_login — отдельный снимок; недоступный аккаунт не роняет остальные."""
    return {login: sync_account(source, login, conversions, period_to) for login in logins}


def sync_metrika(source: MetrikaSource, definition: ConversionDefinition,
                 period_from: date, period_to: date) -> tuple[GoalRow, ...] | SyncFailure:
    """Ошибки API (нет доступа, счётчика, цели, битый ответ) — SyncFailure. Ноль конверсий — это данные, не ошибка."""
    account = f"counter:{definition.counter_id}"
    try:
        available = parse_goals(source.fetch_goals(definition.counter_id))
        if not set(definition.goal_ids) <= available:
            return SyncFailure(account, "goal_not_found")
        spec = MetrikaReportSpec.for_definition(definition, period_from, period_to)
        return parse_bytime(source.fetch_bytime(spec), spec, definition.goal_ids)
    except MetrikaUnavailable as e:
        return SyncFailure(account, e.error_code)
    except ReportFormatError as e:
        return SyncFailure(account, "invalid_report_format", e.code.value)


def with_metrika(snapshot: Snapshot, result: tuple[GoalRow, ...] | SyncFailure) -> Snapshot:
    """Добавить в снимок результат Метрики: данные — как ещё один источник, отказ — как явная отметка."""
    if isinstance(result, SyncFailure):
        return replace(snapshot, source_failures=frozen({"yandex_metrika": result.error_code}))
    return replace(snapshot, sources=snapshot.sources | {"yandex_metrika"}, goal_rows=result)


def capabilities(sources: frozenset[str], has_conversions: bool) -> frozenset[str]:
    """Что доступно правилам: API-источники + «в отчёте Директа есть конверсии по кампаниям»."""
    return frozenset(sources | ({DIRECT_CONVERSIONS} if has_conversions else set()))


def placement_day(r: PlacementRow) -> PlacementDay:
    return PlacementDay(r.campaign_id, placement_id(r.placement), r.date, r.cost, r.clicks, r.conversions,
                        r.placement)


def to_view(snapshot: Snapshot, snapshot_id: int, workspace_id: int, direct_account_id: int) -> SnapshotView:
    days = tuple(CampaignDay(r.campaign_id, r.date, r.cost, r.clicks, r.conversions)
                 for r in snapshot.rows if r.level == "campaign")
    placements = tuple(sorted((placement_day(r) for r in snapshot.rows if isinstance(r, PlacementRow)),
                              key=lambda p: (p.campaign_id, p.date, p.placement_id)))  # порядок как в load_view
    return SnapshotView(snapshot_id, workspace_id, direct_account_id, snapshot.period_from, snapshot.period_to,
                        capabilities(snapshot.sources, snapshot.conversion_definition is not None), days,
                        placement_days=placements, partial_from=snapshot.partial_from)
