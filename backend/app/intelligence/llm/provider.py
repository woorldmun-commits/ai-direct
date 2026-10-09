"""Интерфейс провайдера LLM. Бизнес-логика от конкретного провайдера не зависит (ARCHITECTURE.md §6)."""

from dataclasses import dataclass
from typing import Protocol


class LLMError(Exception):
    """Сбой вызова. Сообщение — код-слаг (`timeout`, `http_500`, `bad_response`), без текста ответа провайдера:
    сырой ответ не попадает ни в исключения, ни в логи."""


@dataclass(frozen=True)
class Completion:
    text: str
    model_version: str


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str, *, max_tokens: int) -> Completion: ...
