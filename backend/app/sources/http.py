"""HTTP-клиент к API Яндекса с безопасным логом: по строке на ответ — провайдер, метод, путь, статус, RequestId,
длительность. Заголовки (Authorization), тело и query-параметры не пишутся никогда: в них токен, названия кампаний,
тексты запросов. Этого достаточно, чтобы найти запрос в поддержке Яндекса по RequestId."""

import logging
import time

import httpx

log = logging.getLogger("ai_direct.http")


# Собственный лог httpx на INFO пишет полный URL с query — оставляем ему только предупреждения.
logging.getLogger("httpx").setLevel(logging.WARNING)


def api_client(provider: str, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """provider: yandex_direct · yandex_metrika · yandex_oauth — метка строки лога. transport — для тестов."""
    def started(request: httpx.Request) -> None:
        request.extensions["started"] = time.monotonic()

    def finished(response: httpx.Response) -> None:
        req = response.request
        ms = round((time.monotonic() - req.extensions.get("started", time.monotonic())) * 1000)
        request_id = response.headers.get("RequestId") or response.headers.get("X-Request-Id")
        log.info("%s %s %s status=%s request_id=%s duration_ms=%s", provider, req.method, req.url.path,
                 response.status_code, request_id, ms)

    return httpx.Client(transport=transport, event_hooks={"request": [started], "response": [finished]})
