"""Единый формат ошибок (API_CONTRACT.md §12): {"error": {"code", "reason"?, "message", "request_id"}}.
Логику клиент строит по code и reason; message — текст для пользователя. Деталей и стека в ответе нет."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

MESSAGES = {
    "invalid_request": "Запрос не по формату.",
    "unauthenticated": "Нужно войти.",
    "csrf_rejected": "Запрос отклонён: неизвестный источник.",
    "forbidden_role": "Недостаточно прав для этого действия.",
    "not_found": "Не найдено.",
    "workspace_deleted": "Рабочее пространство удаляется.",
    "payload_too_large": "Слишком большой запрос.",
    "internal": "Внутренняя ошибка. Попробуйте позже.",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, reason: str | None = None, message: str | None = None):
        super().__init__(code)
        self.status, self.code, self.reason = status, code, reason
        self.message = message or MESSAGES.get(code, MESSAGES["internal"])


def not_found() -> ApiError:
    """Нет объекта или нет доступа — один и тот же ответ: существование чужих данных не раскрывается."""
    return ApiError(404, "not_found")


def error_body(code: str, request_id: str, *, reason: str | None = None, message: str | None = None) -> dict:
    error = {"code": code}
    if reason is not None:
        error["reason"] = reason
    error["message"] = message or MESSAGES.get(code, MESSAGES["internal"])
    error["request_id"] = request_id
    return {"error": error}


def error_response(status: int, code: str, request_id: str, *, reason: str | None = None,
                   headers: dict | None = None) -> JSONResponse:
    return JSONResponse(error_body(code, request_id, reason=reason), status_code=status, headers=headers)


def _request_id(request: Request) -> str:
    return request.scope.get("state", {}).get("request_id", "")


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        body = error_body(exc.code, _request_id(request), reason=exc.reason, message=exc.message)
        return JSONResponse(body, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        # Подробности валидации не возвращаем: в них эхом приходят присланные значения.
        return error_response(400, "invalid_request", _request_id(request))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return error_response(404, "not_found", _request_id(request))
        if exc.status_code == 405:
            return error_response(405, "invalid_request", _request_id(request), reason="method_not_allowed")
        code = "invalid_request" if 400 <= exc.status_code < 500 else "internal"
        return error_response(exc.status_code, code, _request_id(request))
