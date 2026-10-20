"""YandexGPT через Foundation Models (синхронный completion). Все адреса и ключи — только из окружения.

ПРОВЕРИТЬ по документации Yandex Cloud перед включением llm_enabled:
- формат запроса (modelUri, completionOptions.maxTokens строкой, messages[].text) и ответа
  (result.alternatives[0].message.text, result.modelVersion);
- заголовок отключения логирования запросов `x-data-logging-enabled: false` (AI_GOVERNANCE.md §6 п.6,
  ARCHITECTURE.md §2.5): без него текст промпта может храниться у провайдера."""

import os
from dataclasses import dataclass

import httpx

from app.intelligence.llm.provider import Completion, LLMError

TIMEOUT = httpx.Timeout(30.0, connect=5.0)
ENV = ("YANDEXGPT_URL", "YANDEXGPT_MODEL_URI", "YANDEXGPT_FOLDER_ID", "YANDEXGPT_API_KEY")


@dataclass(frozen=True)
class YandexGPTProvider:
    http: httpx.Client
    url: str
    model_uri: str
    folder_id: str
    api_key: str
    name: str = "yandexgpt"

    def __repr__(self) -> str:  # ключ не попадает в логи через repr
        return f"YandexGPTProvider(model={self.model!r})"

    @property
    def model(self) -> str:
        # gpt://<folder>/yandexgpt/latest → yandexgpt/latest: каталог в Agent Run не нужен
        return self.model_uri.split("://", 1)[-1].split("/", 1)[-1]

    @classmethod
    def from_env(cls, http: httpx.Client, env=None) -> "YandexGPTProvider":
        env = os.environ if env is None else env
        missing = [k for k in ENV if not env.get(k)]
        if missing:
            raise LLMError("not_configured")
        return cls(http, *(env[k] for k in ENV))

    def complete(self, system: str, user: str, *, max_tokens: int) -> Completion:
        body = {"modelUri": self.model_uri,
                "completionOptions": {"stream": False, "temperature": 0, "maxTokens": str(max_tokens)},
                "messages": [{"role": "system", "text": system}, {"role": "user", "text": user}]}
        headers = {"Authorization": f"Api-Key {self.api_key}", "x-folder-id": self.folder_id,
                   "x-data-logging-enabled": "false"}
        try:
            r = self.http.post(self.url, json=body, headers=headers, timeout=TIMEOUT)
        except httpx.TimeoutException:
            raise LLMError("timeout") from None
        except httpx.TransportError:
            raise LLMError("transport") from None
        if r.status_code != 200:
            raise LLMError(f"http_{r.status_code}")
        try:
            result = r.json()["result"]
            text = result["alternatives"][0]["message"]["text"]
            version = str(result.get("modelVersion") or "unknown")
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMError("bad_response") from None
        if not isinstance(text, str):
            raise LLMError("bad_response")
        return Completion(text, version)
