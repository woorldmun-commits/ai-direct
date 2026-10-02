"""Граница запроса (чистый ASGI, до маршрутизации): request_id, заголовки безопасности, CSRF по Origin, лимит тела,
и последний рубеж для необработанных исключений — 500 `internal` в том же формате и с теми же заголовками.

Порядок: request_id → CSRF (небезопасный метод с Origin не из allowlist → 403 csrf_rejected) → лимит тела → приложение.
Заголовки безопасности и X-Request-Id добавляются к любому ответу, в том числе к ошибке."""

import json
import logging
import uuid

from app.api.errors import MESSAGES, error_body
from app.api.settings import Settings

log = logging.getLogger("app.api")

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
BASE_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
    (b"cache-control", b"no-store"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
    (b"cross-origin-resource-policy", b"same-origin"),
)
HSTS = (b"strict-transport-security", b"max-age=63072000; includeSubDomains")
_OVERRIDDEN = {name for name, _ in BASE_HEADERS} | {HSTS[0], b"x-request-id"}


class BodyTooLarge(Exception):
    pass


def request_id_from(headers: list[tuple[bytes, bytes]]) -> str:
    """Клиент может прислать свой X-Request-Id — только UUID (иначе в логи и ответ попал бы произвольный текст)."""
    for name, value in headers:
        if name == b"x-request-id":
            try:
                return str(uuid.UUID(value.decode("ascii")))
            except (ValueError, UnicodeDecodeError):
                break
    return str(uuid.uuid4())


def _header(headers: list[tuple[bytes, bytes]], name: bytes) -> bytes | None:
    values = [v for n, v in headers if n == name]
    return values[0] if len(values) == 1 else None  # два Origin / Content-Length — не доверяем ни одному


class BoundaryMiddleware:
    def __init__(self, app, settings: Settings):
        self.app = app
        self.settings = settings
        self.security_headers = BASE_HEADERS + ((HSTS,) if settings.hsts else ())

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = scope.get("headers", [])
        request_id = request_id_from(headers)
        scope.setdefault("state", {})["request_id"] = request_id
        started = False

        async def send_wrapper(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                kept = [(n, v) for n, v in message.get("headers", []) if n.lower() not in _OVERRIDDEN]
                message = {**message, "headers": kept + list(self.security_headers)
                           + [(b"x-request-id", request_id.encode())]}
            await send(message)

        async def reject(status: int, code: str, reason: str | None = None, message: str | None = None):
            body = json.dumps(error_body(code, request_id, reason=reason, message=message),
                              ensure_ascii=False).encode()
            await send_wrapper({"type": "http.response.start", "status": status,
                                "headers": [(b"content-type", b"application/json"),
                                            (b"content-length", str(len(body)).encode())]})
            await send_wrapper({"type": "http.response.body", "body": body})

        if scope["method"] not in SAFE_METHODS and not self._origin_allowed(headers):
            await reject(403, "csrf_rejected")
            return

        limit = self.settings.max_body_bytes
        length = _header(headers, b"content-length")
        if length is not None:
            if not length.isdigit():
                await reject(400, "invalid_request")
                return
            if int(length) > limit:
                await reject(413, "invalid_request", "payload_too_large", MESSAGES["payload_too_large"])
                return
        received = 0

        async def receive_limited():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:  # тело без Content-Length (chunked) или длиннее заявленного
                    raise BodyTooLarge()
            return message

        try:
            await self.app(scope, receive_limited, send_wrapper)
        except BodyTooLarge:
            if not started:
                await reject(413, "invalid_request", "payload_too_large", MESSAGES["payload_too_large"])
        except Exception:
            # Стек — только в лог (с request_id для поиска), клиенту — internal без деталей.
            log.exception("unhandled error", extra={"request_id": request_id})
            if not started:
                await reject(500, "internal")

    def _origin_allowed(self, headers) -> bool:
        origin = _header(headers, b"origin")
        if origin is None:
            return False  # браузер шлёт Origin на изменяющих запросах; без него — не доверяем
        try:
            return origin.decode("ascii").lower() in self.settings.allowed_origins
        except UnicodeDecodeError:
            return False
