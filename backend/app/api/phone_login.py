"""Вход по SMS (API_CONTRACT.md §11) поверх app/auth/phone.py. Юридический HOLD: маршруты подключаются только при
флаге sms_login (app/flags.py, по умолчанию выключен), а сам модуль ещё и под PHONE_AUTH_ENABLED — выключен любой
из двух → 404. Реального SMS-провайдера нет: отправитель — протокол SmsSender (app/api/services.py).

IP для лимитов — только из доверенного прокси (ratelimit.request_ip), IPv6 — по /64 (ratelimit.network_key).
Соединение — из пула без транзакции запроса: phone.py коммитит выдачу кода до отправки SMS.

Завершения входа пока нет: в схеме нет связи «номер → пользователь» (users без телефона). Верный код → 501
not_implemented, код не гасится (consume=False) — когда таблица появится, вход доделывается здесь."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.errors import ApiError, error_response, not_found
from app.api.ratelimit import network_key, request_ip
from app.api.services import service
from app.auth.phone import CaptchaRequired, PhoneAuthDisabled, RateLimited, request_code, verify_code
from app.auth.phone_number import InvalidPhone

router = APIRouter()


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CodeRequest(_Strict):
    phone: Annotated[str, Field(max_length=32)]
    captcha_token: Annotated[str | None, Field(max_length=4096)] = None
    device_id: Annotated[str | None, Field(max_length=128)] = None


class AcceptedDocs(_Strict):
    offer: str | None = None
    pd_consent: str | None = None
    marketing: str | None = None


class CodeVerify(_Strict):
    phone: Annotated[str, Field(max_length=32)]
    code: Annotated[str, Field(max_length=16)]
    accepted: AcceptedDocs | None = None


def _ip(request: Request) -> str:
    ip = request_ip(request.scope, request.app.state.settings.trusted_proxies)
    if ip is None:
        raise ApiError(400, "invalid_request")  # без адреса лимит на IP не работает — не выдаём код
    return network_key(ip)


@router.post("/auth/code/request", status_code=202)
def code_request(request: Request, body: CodeRequest):
    try:
        with request.app.state.pool.connection() as conn:
            result = request_code(conn, config=service(request, "phone_config"), sender=service(request, "sms_sender"),
                                  captcha=service(request, "captcha"), phone=body.phone, ip=_ip(request),
                                  now=datetime.now(timezone.utc), device_id=body.device_id,
                                  captcha_token=body.captcha_token)
    except PhoneAuthDisabled:
        raise not_found() from None
    except InvalidPhone:
        raise ApiError(400, "invalid_request", "invalid_phone") from None
    if isinstance(result, RateLimited):
        return error_response(429, "rate_limited", request.scope["state"]["request_id"],
                              headers={"Retry-After": str(max(1, result.retry_after))})
    if isinstance(result, CaptchaRequired):
        raise ApiError(422, "captcha_required")
    return {}  # одно и то же тело на любой принятый запрос


@router.post("/auth/code/verify")
def code_verify(request: Request, body: CodeVerify):
    try:
        with request.app.state.pool.connection() as conn:
            phone = verify_code(conn, config=service(request, "phone_config"), phone=body.phone, code=body.code,
                                ip=_ip(request), now=datetime.now(timezone.utc), consume=False)
    except PhoneAuthDisabled:
        raise not_found() from None
    if phone is None:
        raise ApiError(401, "invalid_code")
    raise ApiError(501, "not_implemented", "phone_identity_missing")
