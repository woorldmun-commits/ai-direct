"""Паспорт рекомендации, решения человека и состояние команды специалистов: чистая логика без БД."""

from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.active import status_of
from app.api.agents import SPECIALISTS, team_state
from app.api.errors import ApiError
from app.api.recommendation_detail import DecisionInput, parse_id, permitted


# --- Идентификаторы ---------------------------------------------------------------------------------------

def test_parse_id_accepts_only_prefixed_positive_int64():
    assert parse_id("rec_42", "rec") == 42
    assert parse_id("rv_9223372036854775807", "rv") == 2 ** 63 - 1


@pytest.mark.parametrize("raw", ["rec_0", "rec_01", "rv_42", "rec_42 ", "rec_-1", "rec_9223372036854775808", "42"])
def test_parse_id_rejects_everything_else_as_not_found(raw):
    with pytest.raises(ApiError):
        parse_id(raw, "rec")


# --- Разрешённые действия ---------------------------------------------------------------------------------

def card(status="new", insufficient=False, action_level="recommend"):
    return SimpleNamespace(status=status, insufficient=insufficient, action_level=action_level)


@pytest.mark.parametrize("c, role, expected", [
    (card(), "owner", ["view", "postpone", "reject", "accept"]),
    (card(action_level="inspect_only"), "admin", ["view", "postpone", "reject", "check"]),
    (card(insufficient=True), "approver", ["view", "postpone", "reject"]),
    (card(status="accepted"), "owner", ["view", "postpone", "reject"]),  # повторно принять нельзя
    (card(status="applied"), "owner", ["view"]),
    (card(status="rejected"), "owner", ["view"]),
    (card(), "viewer", ["view"]),
])
def test_permitted_actions(c, role, expected):
    assert permitted(c, role) == expected


# --- Тело решения -----------------------------------------------------------------------------------------

def test_decision_input_valid_variants():
    DecisionInput(action="accept", version_id="rv_1")
    DecisionInput(action="postpone", version_id="rv_1", until=date(2026, 11, 1))
    DecisionInput(action="reject", version_id="rv_1", reason="other", comment="нет")


@pytest.mark.parametrize("body", [
    {"action": "postpone", "version_id": "rv_1"},                                   # нет until
    {"action": "accept", "version_id": "rv_1", "until": "2026-11-01"},              # until не к месту
    {"action": "reject", "version_id": "rv_1"},                                     # нет причины
    {"action": "accept", "version_id": "rv_1", "comment": "x"},                     # комментарий только к reject
    {"action": "reject", "version_id": "rv_1", "reason": "other", "comment": "x" * 1001},
    {"action": "apply", "version_id": "rv_1"},                                      # изменения в кабинете не делаем
    {"action": "accept", "version_id": "rec_1"},
    {"action": "accept", "version_id": "rv_1", "extra": 1},
])
def test_decision_input_rejects_invalid(body):
    with pytest.raises(ValidationError):
        DecisionInput(**body)


# --- Статус и команда специалистов ------------------------------------------------------------------------

def test_accepted_is_its_own_status():
    assert status_of("accepted", None, date(2026, 10, 3)) == "accepted"


def by_id(state):
    return {s["id"]: s for s in state["specialists"]}


def test_team_without_audit_needs_data_everywhere():
    state = team_state(None, set())
    assert state["mode"] == "recommendations_only" and state["coordinator"]["status"] == "needs_data"
    assert all(s["status"] == "needs_data" for s in state["specialists"])
    assert len(state["specialists"]) == len(SPECIALISTS)


def test_team_status_follows_audited_rule_families_only():
    audit = {"rules_skipped": [{"rule": "zero_conv_placements@1"}]}
    state = by_id(team_state(audit, {"high_cpa", "zero_conv_placements"}, metrika=True))
    assert state["data_quality"]["status"] == "available"
    assert state["direct_search"]["status"] == "available" and state["direct_search"]["rule_families"] == ["high_cpa"]
    assert state["rsya"]["status"] == "needs_data"  # правило пропущено: недостаточно данных
    # нереализованный анализ не становится «доступным» даже при подключённой Метрике
    assert state["measurement"]["status"] == "needs_data"
    assert "Этот специализированный анализ ещё не реализован" in state["measurement"]["missing_data"]
