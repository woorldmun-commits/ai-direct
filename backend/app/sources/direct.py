"""Источник отчётов Яндекс.Директа (ARCHITECTURE.md §2.7). Источник отдаёт сырой TSV — разбор и allowlist
в sync/parse.py, чтобы новый столбец API не мог попасть в снимок в обход парсера: бизнес-логика видит StatRow.

Реализации: DirectFixture (тесты, разработка) и DirectApi (Reports API v501, api или sandbox)."""

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import NoReturn, Protocol

import httpx

from app.sources.conversion import ConversionDefinition

# Заголовки запроса Reports API: деньги десятичными рублями, без строки заголовка отчёта и итоговой строки.
# Строка с именами столбцов остаётся — по ней парсер проверяет, что API вернул ровно запрошенное.
REPORT_HEADERS = {
    "processingMode": "auto",
    "returnMoneyInMicros": "false",
    "skipReportHeader": "true",
    "skipReportSummary": "true",
}


@dataclass(frozen=True)
class ReportSpec:
    report_type: str
    level: str
    fields: tuple[str, ...]  # запрашиваем только то, что храним


CAMPAIGN_REPORT = ReportSpec("CAMPAIGN_PERFORMANCE_REPORT", "campaign",
                             ("Date", "CampaignId", "Impressions", "Clicks", "Cost"))
QUERY_REPORT = ReportSpec("SEARCH_QUERY_PERFORMANCE_REPORT", "query",
                          ("Date", "CampaignId", "Query", "Impressions", "Clicks", "Cost"))


# Три класса ошибок Директа (ARCHITECTURE.md §2.6):
#   доступ к аккаунту  → direct_accounts.status = unavailable(причина); синхронизации пропускает guard, вернуть — recheck;
#   подключение/токен  → direct_connections.status = причина; вернуть — recheck (или новый OAuth при token_revoked);
#   данные и временные → только sync_run: Failed (формат, report_timeout, invalid_request) или RetryAt
#                        (отчёт строится: 201/202 + retryIn; сервер недоступен, баллы, соединения).
ACCOUNT_ERRORS = frozenset({"access_denied", "account_not_found", "api_restricted"})
CONNECTION_ERRORS = frozenset({"token_expired", "token_revoked", "permission_missing"})


class AccountUnavailable(Exception):
    """Нет доступа к аккаунту (Client-Login): отозван доступ, аккаунт удалён, нет прав у представителя."""

    def __init__(self, login: str, error_code: str):
        assert error_code in ACCOUNT_ERRORS, error_code
        super().__init__(f"{login}: {error_code}")
        self.login, self.error_code = login, error_code


class ConnectionUnavailable(Exception):
    """Токен подключения не действует: истёк, отозван, не хватает прав (scope)."""

    def __init__(self, error_code: str):
        assert error_code in CONNECTION_ERRORS, error_code
        super().__init__(error_code)
        self.error_code = error_code


class RetryLater(Exception):
    """Отчёт ещё формируется (201/202 + retryIn) или временная ошибка API (сервер, баллы, соединения): вернуть задачу
    в очередь через retry_in секунд — интервал задаёт сервер, воркер не спит в процессе."""

    def __init__(self, retry_in: int, reason: str = "report_not_ready"):
        super().__init__(f"{reason}: retry in {retry_in}s")
        self.retry_in, self.reason = retry_in, reason


class DirectApiError(Exception):
    """Запрос отклонён по причине, которую повтор не исправит (8000 некорректный запрос, 8312 и т. п.).
    request_id — для обращения в поддержку Яндекса; текст ошибки сервера не храним и не показываем."""

    def __init__(self, error_code: int, request_id: str | None):
        if not re.fullmatch(r"[\w-]{1,64}", str(request_id or "")):  # пишется в логи и артефакты — без переводов строк
            request_id = None
        super().__init__(f"direct api error {error_code} (request {request_id})")
        self.error_code, self.request_id = error_code, request_id


class DirectSource(Protocol):
    def fetch_report(self, login: str, spec: ReportSpec, conversions: ConversionDefinition | None,
                     date_from: date, date_to: date) -> str: ...

    def check_access(self, login: str) -> None:
        """Лёгкий авторизованный запрос (DirectApi: Campaigns.get, 1 объект) — только проверка доступа.
        Бросает ConnectionUnavailable / AccountUnavailable / RetryLater."""


class DirectFixture:
    """Отчёты из файлов <root>/<login>/<report_type>.tsv. Ошибки: <root>/connection_error — код ошибки токена,
    <root>/<login>/unavailable — код ошибки доступа к аккаунту; каталога аккаунта нет — account_not_found."""

    def __init__(self, root: Path):
        self.root = root

    def _account(self, login: str) -> Path:
        if (self.root / "connection_error").exists():
            raise ConnectionUnavailable((self.root / "connection_error").read_text(encoding="utf-8").strip())
        account = self.root / login
        if not account.exists():
            raise AccountUnavailable(login, "account_not_found")
        if (account / "unavailable").exists():
            raise AccountUnavailable(login, (account / "unavailable").read_text(encoding="utf-8").strip())
        return account

    def check_access(self, login: str) -> None:
        self._account(login)

    def fetch_report(self, login, spec, conversions, date_from, date_to) -> str:
        return (self._account(login) / f"{spec.report_type}.tsv").read_text(encoding="utf-8")


# --- Reports API ----------------------------------------------------------------------------------------------

API_URL = {"api": "https://api.direct.yandex.com/json", "sandbox": "https://api-sandbox.direct.yandex.com/json"}
DEFAULT_RETRY_IN = 60  # если сервер не прислал retryIn

# Коды ошибок Директа (concepts/errors-list) → классы источника. Не перечисленные — DirectApiError (повтор не поможет).
_ERRORS = {
    53: lambda login: ConnectionUnavailable("token_expired"),      # токен не принят: нужен refresh или новый OAuth
    513: lambda login: ConnectionUnavailable("permission_missing"),  # логин токена не подключён к Директу
    54: lambda login: AccountUnavailable(login, "access_denied"),   # нет прав на аккаунт (Client-Login)
    8800: lambda login: AccountUnavailable(login, "account_not_found"),
    3000: lambda login: AccountUnavailable(login, "api_restricted"),
    3001: lambda login: AccountUnavailable(login, "api_restricted"),
}
_TEMPORARY = frozenset({52, 152, 506, 1000, 1001, 1002})  # сервер авторизации/API, баллы, соединения


def json_body(r: httpx.Response) -> dict:
    """Тело-объект JSON или {}: шлюз может вернуть HTML, а сбойный ответ — не объект."""
    try:
        body = r.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def raise_for_direct_error(r: httpx.Response, login: str) -> NoReturn:
    """Ответ не 200 → исключение источника. Тело ошибки — JSON {"error": {error_code, request_id, …}}."""
    err = json_body(r).get("error")
    err = err if isinstance(err, dict) else {}
    code = int(err.get("error_code") or 0)
    retry_in = int(r.headers.get("retryIn") or DEFAULT_RETRY_IN)
    if code in _ERRORS:
        raise _ERRORS[code](login)
    if code in _TEMPORARY or (not code and r.status_code >= 500):
        raise RetryLater(retry_in, "api_unavailable")
    raise DirectApiError(code or r.status_code, err.get("request_id") or r.headers.get("RequestId"))


@dataclass(frozen=True)
class DirectApi:
    """Reports API v501 — только чтение. Один объект на запуск синхронизации: run_key (id sync_run) даёт стабильный
    ReportName — повтор после 201/202 приходит с тем же именем и теми же параметрами, как требует офлайн-режим,
    а новая синхронизация того же дня не получит из очереди старый отчёт.
    ponytail: лимиты пользователя Яндекса (20 запросов / 10 с, 5 офлайн-отчётов) — общий ограничитель на Redis
    вместе с очередью задач; сейчас их превышение приходит временной ошибкой API → RetryLater."""
    http: httpx.Client
    access_token: str = field(repr=False)
    run_key: str
    env: str = "api"  # api · sandbox

    def _headers(self, login: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}", "Client-Login": login, "Accept-Language": "ru"}

    def report_body(self, spec: ReportSpec, conversions: ConversionDefinition | None,
                    date_from: date, date_to: date) -> dict:
        if date_from > date_to:
            raise ValueError(f"период задом наперёд: {date_from} > {date_to}")
        params = {
            "SelectionCriteria": {"DateFrom": date_from.isoformat(), "DateTo": date_to.isoformat()},
            # Conversions последним: API разворачивает его в Conversions_<цель>_<модель> на этом месте —
            # порядок столбцов совпадает с тем, что ждёт парсер
            "FieldNames": list(spec.fields) + (["Conversions"] if conversions else []),
            "ReportName": f"ai-direct:{self.run_key}:{spec.report_type}",
            "ReportType": spec.report_type,
            "DateRangeType": "CUSTOM_DATE",
            "Format": "TSV",
            "IncludeVAT": "YES",  # фактические расходы клиента
        }
        if conversions:  # цели и модель выбирает ConversionDefinition, не клиент API
            params["Goals"] = [str(g) for g in conversions.goal_ids]
            params["AttributionModels"] = [conversions.direct_attribution()]
        return {"params": params}

    def fetch_report(self, login: str, spec: ReportSpec, conversions: ConversionDefinition | None,
                     date_from: date, date_to: date) -> str:
        try:
            r = self.http.post(f"{API_URL[self.env]}/v501/reports", timeout=60,
                               json=self.report_body(spec, conversions, date_from, date_to),
                               headers={**self._headers(login), **REPORT_HEADERS})
        except httpx.TransportError:
            raise RetryLater(DEFAULT_RETRY_IN, "api_unavailable") from None
        if r.status_code == 200:
            return r.text
        if r.status_code in (201, 202):  # поставлен в очередь / ещё строится — повторить с теми же параметрами
            raise RetryLater(int(r.headers.get("retryIn") or DEFAULT_RETRY_IN), "report_not_ready")
        raise_for_direct_error(r, login)

    def check_access(self, login: str) -> None:
        """Лёгкий авторизованный запрос: одна кампания, только Id."""
        body = {"method": "get", "params": {"SelectionCriteria": {}, "FieldNames": ["Id"], "Page": {"Limit": 1}}}
        try:
            r = self.http.post(f"{API_URL[self.env]}/v5/campaigns", json=body, headers=self._headers(login), timeout=30)
        except httpx.TransportError:
            raise RetryLater(DEFAULT_RETRY_IN, "api_unavailable") from None
        if r.status_code == 200 and "error" not in json_body(r):
            return
        raise_for_direct_error(r, login)
