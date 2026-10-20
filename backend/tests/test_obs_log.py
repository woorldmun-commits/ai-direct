"""Структурный лог: одна строка JSON на запись, только поля из allowlist, контекст задачи, без текста исключения."""

import json
import logging

from app.obs.log import JsonFormatter, bind


def render(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def record(msg="job done", *args, exc_info=None, **extra) -> logging.LogRecord:
    r = logging.LogRecord("ai_direct.worker", logging.INFO, __file__, 1, msg, args, exc_info)
    r.__dict__.update(extra)
    return r


def test_line_is_json_with_base_fields():
    out = render(record("sync %s", 7))
    assert out["level"] == "INFO" and out["logger"] == "ai_direct.worker" and out["msg"] == "sync 7"
    assert out["ts"].endswith("Z")


def test_allowlisted_extras_only():
    out = render(record(request_id="r-1", workspace_id=5, job="notify", duration_ms=12,
                        login="client-secret", token="y0_SECRET"))
    assert out["request_id"] == "r-1" and out["workspace_id"] == 5 and out["job"] == "notify"
    assert "login" not in out and "token" not in out
    assert "client-secret" not in json.dumps(out) and "y0_SECRET" not in json.dumps(out)


def test_bind_adds_context_and_restores():
    with bind(job="measure", workspace_id=3):
        inner = render(record())
    outer = render(record())
    assert inner["job"] == "measure" and inner["workspace_id"] == 3
    assert "job" not in outer and "workspace_id" not in outer


def test_exception_type_and_stack_without_message():
    try:
        raise ValueError("client-login@example.ru")  # текст исключения может нести данные клиента
    except ValueError:
        import sys
        out = render(record("job failed", exc_info=sys.exc_info()))
    assert out["exc_type"] == "ValueError"
    assert "test_obs_log.py" in out["stack"][-1]
    assert "client-login@example.ru" not in json.dumps(out)
