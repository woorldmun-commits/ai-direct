"""HTTP-клиент к API Яндекса с безопасным логом: по строке на ответ — провайдер, метод, путь, статус, RequestId,
длительность. Заголовки (Authorization), тело и query-параметры не пишутся никогда: в них токен, названия кампаний,
тексты запросов. Этого достаточно, чтобы найти запрос в поддержке Яндекса по RequestId.

Здесь же — общая устойчивость клиентов: лимит запросов на пользователя и предел размера ответа."""

import hashlib
import logging
import re
import threading
import time
from collections import defaultdict, deque
from typing import Callable

import httpx

log = logging.getLogger("ai_direct.http")


class ResponseTooLarge(Exception):
    """Ответ больше предела: дочитывать его в память воркера нельзя."""


def user_key(access_token: str) -> str:
    """Ключ лимитов пользователя Яндекса — хэш токена: сам токен не хранится даже в памяти лимитера."""
    return hashlib.sha256(access_token.encode()).hexdigest()[:16]


class RateLimiter:
    """Не больше limit запросов за window секунд на ключ (пользователя Яндекса), скользящее окно. Свободного слота
    нет — ждёт (не дольше window): короче, чем вернуть задачу в очередь и заново запросить все отчёты.
    ponytail: память одного процесса; при нескольких воркерах — общий счётчик (Redis или PostgreSQL)."""

    def __init__(self, limit: int, window: float, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.limit, self.window, self.clock, self.sleep = limit, window, clock, sleep
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def acquire(self, key: str) -> None:
        while True:
            with self._lock:
                now, calls = self.clock(), self._calls[key]
                while calls and calls[0] <= now - self.window:
                    calls.popleft()
                if len(calls) < self.limit:
                    calls.append(now)
                    return
                wait = calls[0] + self.window - now
            self.sleep(wait)


def read_limited(http: httpx.Client, method: str, url: str, *, max_bytes: int, **kwargs) -> httpx.Response:
    """Запрос с пределом размера ответа (после распаковки): заявленный Content-Length больше предела — отказ без
    чтения, иначе тело читается частями и обрывается на пределе. Возвращает прочитанный ответ."""
    with http.stream(method, url, **kwargs) as r:
        declared = r.headers.get("Content-Length", "")
        if declared.isdigit() and int(declared) > max_bytes:
            raise ResponseTooLarge(f"{declared} > {max_bytes}")
        body = bytearray()
        for chunk in r.iter_bytes():
            body += chunk
            if len(body) > max_bytes:
                raise ResponseTooLarge(f"> {max_bytes}")
    # тело уже распаковано: без Content-Encoding/Length новый ответ не распакует его второй раз
    headers = [(k, v) for k, v in r.headers.multi_items() if k.lower() not in ("content-encoding", "content-length")]
    return httpx.Response(r.status_code, headers=headers, content=bytes(body), request=r.request)


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
        if request_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
            request_id = None
        log.info("%s %s %s status=%s request_id=%s duration_ms=%s", provider, req.method, req.url.path,
                 response.status_code, request_id, ms)

    return httpx.Client(transport=transport, follow_redirects=False,
                        event_hooks={"request": [started], "response": [finished]})
