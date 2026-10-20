"""Лимит частоты запросов на вход и дорогие запросы (ASGI, до маршрутизации) и адрес клиента.

Адрес клиента — адрес соединения; X-Forwarded-For читается, только если соединение пришло от доверенного прокси
(API_TRUSTED_PROXIES), и берётся крайний правый адрес не из доверенных: левые части цепочки клиент пишет сам.
IPv6 агрегируется по /64 — у одного абонента обычно вся подсеть, иначе лимит обходится сменой адреса.

ponytail: счётчики в памяти одного процесса, окно фиксированное. Для нескольких инстансов (или воркеров uvicorn)
нужен общий стор (Redis / PostgreSQL) — иначе лимит умножается на число процессов."""

import ipaddress
import json
import re
import time
from typing import Callable

from app.api.errors import error_body

WINDOW = 60  # секунд
# Вход и OAuth-колбэки — мало запросов на человека, перебор и спам кодов — много.
AUTH = re.compile(r"^/api/v1/(auth/|integrations/[a-z_]+/callback$)")
# Запросы, которые считают exposure по снимкам или ходят в Яндекс.
EXPENSIVE = re.compile(r"^/api/v1/workspaces/[^/]+/(today|recommendations(/.*)?|integrations/[a-z_]+/connect)$")
LIMITS = {"auth": 20, "expensive": 120}  # запросов в окно с одного адреса (/64)


def network_key(ip: str) -> str:
    """Ключ лимита: IPv4 — адрес, IPv6 — его /64."""
    addr = ipaddress.ip_address(ip)
    if addr.version == 4:
        return str(addr)
    if addr.ipv4_mapped is not None:
        return str(addr.ipv4_mapped)
    return str(ipaddress.ip_network(f"{addr}/64", strict=False))


def client_ip(peer: str | None, forwarded: list[str], trusted: frozenset) -> str | None:
    """Адрес клиента. forwarded — все значения X-Forwarded-For по порядку."""
    try:
        current = ipaddress.ip_address(peer) if peer else None
    except ValueError:
        return None  # testclient и unix-сокеты: адреса нет
    chain = [p.strip() for v in forwarded for p in v.split(",")]
    while current is not None and any(current in n for n in trusted) and chain:
        try:
            current = ipaddress.ip_address(chain.pop())
        except ValueError:
            break  # мусор в цепочке: дальше не верим, остаёмся на последнем проверенном адресе
    return str(current) if current is not None else None


def request_ip(scope, trusted: frozenset) -> str | None:
    forwarded = [v.decode("latin-1") for n, v in scope.get("headers", []) if n == b"x-forwarded-for"]
    return client_ip((scope.get("client") or (None,))[0], forwarded, trusted)


def bucket(path: str) -> str | None:
    if AUTH.match(path):
        return "auth"
    if EXPENSIVE.match(path):
        return "expensive"
    return None


class RateLimitMiddleware:
    def __init__(self, app, trusted: frozenset = frozenset(), limits: dict | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.app, self.trusted, self.limits, self.clock = app, trusted, limits or LIMITS, clock
        self.window, self.counts = -1, {}

    async def __call__(self, scope, receive, send):
        name = bucket(scope["path"]) if scope["type"] == "http" else None
        ip = request_ip(scope, self.trusted) if name else None
        if name is None or ip is None:
            await self.app(scope, receive, send)
            return
        now = self.clock()
        window = int(now // WINDOW)
        if window != self.window:
            self.window, self.counts = window, {}  # прошлое окно больше не нужно — память не растёт
        key = (name, network_key(ip))
        self.counts[key] = self.counts.get(key, 0) + 1
        if self.counts[key] <= self.limits[name]:
            await self.app(scope, receive, send)
            return
        retry = str(max(1, int((window + 1) * WINDOW - now)))
        body = json.dumps(error_body("rate_limited", scope.get("state", {}).get("request_id", "")),
                          ensure_ascii=False).encode()
        await send({"type": "http.response.start", "status": 429,
                    "headers": [(b"content-type", b"application/json"), (b"retry-after", retry.encode()),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
