"""LLM-шлюз: YandexGPT через httpx.MockTransport (сети нет), один повтор, схема, сырой ответ не в логах."""

import json
import logging

import httpx
import pytest

from app.intelligence.llm.gateway import (MAX_OUTPUT_TOKENS, PROMPT_HASH, PROMPT_VERSION, LLMGateway,
                                          parse_answer)
from app.intelligence.llm.provider import Completion, LLMError
from app.intelligence.llm.yandexgpt import YandexGPTProvider

ENV = {"YANDEXGPT_URL": "https://llm.example/completion", "YANDEXGPT_MODEL_URI": "gpt://folder1/yandexgpt/latest",
       "YANDEXGPT_FOLDER_ID": "folder1", "YANDEXGPT_API_KEY": "test-key"}
GOOD = {"summary": "Итог", "claims": [{"type": "OBSERVATION", "text": "Расход 100 ₽", "evidence_ids": ["e1"],
                                        "causal_status": "descriptive", "key": True}]}


def yandex_response(text: str, status: int = 200) -> httpx.Response:
    body = {"result": {"alternatives": [{"message": {"role": "assistant", "text": text}, "status": "FINAL"}],
                       "modelVersion": "23.10.2024"}}
    return httpx.Response(status, json=body)


def provider(handler) -> YandexGPTProvider:
    return YandexGPTProvider.from_env(httpx.Client(transport=httpx.MockTransport(handler)), ENV)


def test_request_shape_headers_and_parsed_completion():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["headers"] = request.headers
        return yandex_response("ok")

    c = provider(handler).complete("sys", "usr", max_tokens=100)
    assert c == Completion("ok", "23.10.2024")
    assert seen["body"]["modelUri"] == ENV["YANDEXGPT_MODEL_URI"]
    assert seen["body"]["completionOptions"]["maxTokens"] == "100"
    assert [m["role"] for m in seen["body"]["messages"]] == ["system", "user"]
    assert seen["headers"]["authorization"] == "Api-Key test-key"
    assert seen["headers"]["x-data-logging-enabled"] == "false"


def test_model_hides_folder_and_repr_hides_key():
    p = provider(lambda r: yandex_response("ok"))
    assert p.model == "yandexgpt/latest"
    assert "test-key" not in repr(p)


def test_missing_env_is_not_configured():
    with pytest.raises(LLMError, match="not_configured"):
        YandexGPTProvider.from_env(httpx.Client(), {**ENV, "YANDEXGPT_API_KEY": ""})


@pytest.mark.parametrize("response, code", [
    (httpx.Response(500, text="secret body"), "http_500"),
    (httpx.Response(200, json={"oops": 1}), "bad_response"),
    (httpx.Response(200, text="not json"), "bad_response"),
])
def test_provider_errors_are_slugs_without_body(response, code):
    with pytest.raises(LLMError) as e:
        provider(lambda r: response).complete("s", "u", max_tokens=10)
    assert str(e.value) == code


def test_timeout_is_an_llm_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)
    with pytest.raises(LLMError, match="timeout"):
        provider(handler).complete("s", "u", max_tokens=10)


def test_gateway_success_carries_versions_and_limit():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return yandex_response(json.dumps(GOOD))

    result = LLMGateway(provider(handler)).generate({"facts": []})
    assert result.answer is not None and result.answer.claims[0].evidence_ids == ["e1"]
    assert (result.provider, result.model, result.model_version) == ("yandexgpt", "yandexgpt/latest", "23.10.2024")
    assert (result.prompt_version, result.prompt_hash, result.attempts) == (PROMPT_VERSION, PROMPT_HASH, 1)
    assert calls[0]["completionOptions"]["maxTokens"] == str(MAX_OUTPUT_TOKENS)
    assert len(PROMPT_HASH) == 64


def test_invalid_then_valid_uses_one_retry():
    answers = iter(["не json", json.dumps(GOOD)])
    result = LLMGateway(provider(lambda r: yandex_response(next(answers)))).generate({})
    assert result.answer is not None and result.attempts == 2


def test_invalid_twice_gives_none_and_logs_no_raw_text(caplog):
    calls = []

    def handler(request):
        calls.append(1)
        return yandex_response("RAW-SECRET-ANSWER")

    with caplog.at_level(logging.DEBUG):
        result = LLMGateway(provider(handler)).generate({})
    assert result.answer is None and result.error_code == "invalid_schema" and len(calls) == 2
    assert "RAW-SECRET-ANSWER" not in caplog.text


def test_transport_failure_twice_gives_none():
    result = LLMGateway(provider(lambda r: httpx.Response(503))).generate({})
    assert result.answer is None and result.error_code == "http_503" and result.model_version == "unknown"


def test_oversized_prompt_is_not_sent():
    calls = []
    result = LLMGateway(provider(lambda r: calls.append(1) or yandex_response("x"))).generate({"x": "a" * 30_000})
    assert result.answer is None and result.error_code == "prompt_too_large" and not calls


@pytest.mark.parametrize("text", [
    json.dumps({**GOOD, "extra": 1}),                                   # лишнее поле
    json.dumps({"summary": "s", "claims": []}),                         # нет утверждений
    json.dumps({"summary": "s", "claims": [{**GOOD["claims"][0], "evidence_ids": "e1"}]}),  # не список
    "[1, 2]",
])
def test_schema_is_strict(text):
    assert parse_answer(text) is None


def test_code_fence_is_tolerated():
    assert parse_answer("```json\n" + json.dumps(GOOD) + "\n```") is not None
