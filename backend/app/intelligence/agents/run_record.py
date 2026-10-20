"""Запись Agent Run (docs/INTELLIGENCE_V2_CONTRACTS.md §1). Только структура: в БД не пишет.
Пустое LLM-поле (None) значит «не применялось», а не нуль; детерминированный запуск без LLM валиден."""

import re
from dataclasses import dataclass
from datetime import datetime

from app.intelligence.contracts._validate import check_ident, check_ident_tuple
from app.intelligence.contracts.sufficiency import DataSufficiency

_HASH = re.compile(r"[0-9a-f]{64}")
_SLUG = re.compile(r"[a-z0-9_]{1,64}")
_STATUSES = ("completed", "failed", "refused")
_LLM_FIELDS = ("model", "model_version", "prompt_version", "prompt_hash")
_COUNTS = ("decision_count", "recommendation_count", "explanation_count")


@dataclass(frozen=True)
class AgentRunRecord:
    run_id: str
    workspace_id: int
    started_at: datetime
    completed_at: datetime | None
    status: str
    agent_version: str
    rule_version: str
    input_bundle_hash: str
    source_snapshot_ids: tuple[int, ...]
    metric_versions: tuple[str, ...]
    data_status: str
    data_sufficiency: DataSufficiency
    analysis_run_id: int | None = None
    analysis_plan_id: int | None = None
    release_id: str | None = None
    provider: str | None = None
    model: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    prompt_hash: str | None = None
    knowledge_pack_version: str | None = None
    knowledge_pack_hash: str | None = None
    business_context_version: str | None = None
    capabilities_used: tuple[str, ...] = ()
    tools_used: tuple[str, ...] = ()
    latency_ms: int | None = None
    output_hash: str | None = None
    decision_count: int = 0
    recommendation_count: int = 0
    explanation_count: int = 0
    refusal_reason: str | None = None
    error_code: str | None = None

    def __post_init__(self):
        self._check_shape()
        if self.status not in _STATUSES or self.data_status not in ("complete", "partial"):
            raise ValueError(f"status / data_status: {self.status!r} / {self.data_status!r}")
        self._check_time()
        for name in ("input_bundle_hash", "output_hash", "prompt_hash", "knowledge_pack_hash"):
            value = getattr(self, name)
            if value is not None and not _HASH.fullmatch(value):
                raise ValueError(f"{name}: ожидается sha256 hex")
        if any(not isinstance(getattr(self, n), int) or getattr(self, n) < 0 for n in _COUNTS):
            raise ValueError("счётчики — целые >= 0")
        if self.latency_ms is not None and (not isinstance(self.latency_ms, int) or self.latency_ms < 0):
            raise ValueError("latency_ms: целое >= 0")
        if self.data_sufficiency is DataSufficiency.INSUFFICIENT and self.recommendation_count:
            raise ValueError("recommendation_count: при недостаточных данных рекомендаций быть не может")
        self._check_llm()
        self._check_outcome()

    def _check_shape(self) -> None:
        for name in ("run_id", "agent_version", "rule_version"):
            check_ident(name, getattr(self, name))
        for name in ("metric_versions", "capabilities_used", "tools_used"):
            check_ident_tuple(name, getattr(self, name))
        ids = self.source_snapshot_ids  # id снимков в БД — bigint
        if (not isinstance(ids, tuple) or not all(isinstance(i, int) and not isinstance(i, bool) and i > 0
                                                  for i in ids)):
            raise ValueError("source_snapshot_ids: ожидается tuple положительных int")
        if not isinstance(self.workspace_id, int) or isinstance(self.workspace_id, bool) or self.workspace_id < 1:
            raise ValueError("workspace_id: положительный int")
        if not isinstance(self.data_sufficiency, DataSufficiency):
            raise ValueError("data_sufficiency: ожидается DataSufficiency")

    def _check_time(self) -> None:
        if self.status == "completed" and self.completed_at is None:
            raise ValueError("completed_at обязателен при status = completed")
        if self.started_at.tzinfo is None or (self.completed_at is not None and self.completed_at.tzinfo is None):
            raise ValueError("время запуска — с часовым поясом")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at раньше started_at")

    def _check_llm(self) -> None:
        if self.provider is None:
            if any(getattr(self, n) is not None for n in _LLM_FIELDS):
                raise ValueError("llm-поля заданы без provider")
        elif any(getattr(self, n) is None for n in _LLM_FIELDS):
            raise ValueError("llm-запуск: нужны model, model_version, prompt_version, prompt_hash")

    def _check_outcome(self) -> None:
        for name in ("refusal_reason", "error_code"):  # код-слаг, не текст исключения
            value = getattr(self, name)
            if value is not None and not _SLUG.fullmatch(value):
                raise ValueError(f"{name}: ожидается [a-z0-9_]{{1,64}}")
        if (self.status == "refused") != (self.refusal_reason is not None):
            raise ValueError("refusal_reason задаётся тогда и только тогда, когда status = refused")
        if (self.status == "failed") != (self.error_code is not None):
            raise ValueError("error_code задаётся тогда и только тогда, когда status = failed")


def record_for_deterministic_run(*, run_id: str, workspace_id: int, started_at: datetime, completed_at: datetime,
                                 agent_version: str, rule_version: str, input_bundle_hash: str,
                                 source_snapshot_ids: tuple[int, ...], metric_versions: tuple[str, ...],
                                 data_status: str, data_sufficiency: DataSufficiency, output_hash: str,
                                 decision_count: int, recommendation_count: int,
                                 **optional) -> AgentRunRecord:
    """Запуск без LLM (llm_enabled=false): provider / model / prompt* и пакет знаний пусты, путь — шаблон."""
    return AgentRunRecord(run_id=run_id, workspace_id=workspace_id, started_at=started_at,
                          completed_at=completed_at, status="completed", agent_version=agent_version,
                          rule_version=rule_version, input_bundle_hash=input_bundle_hash,
                          source_snapshot_ids=source_snapshot_ids, metric_versions=metric_versions,
                          data_status=data_status, data_sufficiency=data_sufficiency, output_hash=output_hash,
                          decision_count=decision_count, recommendation_count=recommendation_count, **optional)
