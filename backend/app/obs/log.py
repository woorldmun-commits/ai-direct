"""Структурный лог: одна строка JSON на запись — для сбора логов (Cloud Logging) без разбора текста.

В строку попадают только сообщение и поля из allowlist (FIELDS): ID, коды, тайминги. Произвольные extra, текст
исключения и строки исходного кода в трассировке не пишутся — в них могут оказаться логин, токен или название
кампании (ARCHITECTURE.md §2.4: в логах только ID, статусы и тайминги). Контекст задачи воркера — bind()."""

import json
import logging
import os
import sys
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Iterator

FIELDS = ("request_id", "workspace_id", "job", "result", "duration_ms", "status", "error_code")
_context: ContextVar[dict] = ContextVar("log_context", default={})


@contextmanager
def bind(**fields) -> Iterator[None]:
    """Поля контекста (job, workspace_id, request_id) для всех записей внутри блока; на выходе — прежние."""
    token = _context.set({**_context.get(), **fields})
    try:
        yield
    finally:
        _context.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": datetime.fromtimestamp(record.created, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
               "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        context = _context.get()
        for name in FIELDS:
            value = getattr(record, name, context.get(name))
            if value is not None:
                out[name] = value
        if record.exc_info and record.exc_info[0]:
            exc_type, _, tb = record.exc_info
            out["exc_type"] = exc_type.__name__
            out["stack"] = [f"{f.filename}:{f.lineno} {f.name}" for f in traceback.extract_tb(tb)]
        return json.dumps(out, ensure_ascii=False, default=str)


def setup(level: str | None = None) -> None:
    """Корневой обработчик → stdout в JSON. Уровень — LOG_LEVEL (по умолчанию INFO)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level or os.environ.get("LOG_LEVEL", "INFO"))
