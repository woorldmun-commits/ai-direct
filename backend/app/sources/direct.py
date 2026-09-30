"""Источник отчётов Яндекс.Директа (ARCHITECTURE.md §2.7). Источник отдаёт сырой TSV — разбор и allowlist
в sync/parse.py, чтобы новый столбец API не мог попасть в снимок в обход парсера.

Реализации: DirectFixture (тесты и разработка до одобрения API). DirectApi и DirectSandbox — когда будет доступ к API."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

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
#   данные и временные → только sync_run: Failed (формат, report_timeout) или RetryAt (retryIn, 429).
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
    """Отчёт ещё формируется (201/202 + retryIn) или превышен лимит (429): вернуть задачу в очередь через retry_in
    секунд — интервал задаёт сервер, воркер не спит в процессе."""

    def __init__(self, retry_in: int, reason: str = "report_not_ready"):
        super().__init__(f"{reason}: retry in {retry_in}s")
        self.retry_in, self.reason = retry_in, reason


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
