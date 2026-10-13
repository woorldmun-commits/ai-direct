"""Recommendation passport and append-only decisions bound to the current audited version."""

import re
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, model_validator
from psycopg.types.json import Jsonb

from app.api.active import active_cards, today_msk, with_exposure
from app.api.deps import Conn, CurrentWorkspace
from app.api.errors import ApiError, not_found
from app.api.serialize import ext, moment, recommendation_item, value

router = APIRouter()
EDITORS = {"owner", "admin", "approver"}
EVENTS = {"accept": "accepted", "postpone": "postponed", "reject": "rejected", "check": "checked"}
DECISIONS = {"accepted": "accepted", "postponed": "postponed", "rejected": "rejected",
             "checked": "recommendation_checked", "done": "manual_claimed"}


def parse_id(raw: str, prefix: str) -> int:
    if not re.fullmatch(prefix + "_[1-9][0-9]{0,18}", raw):
        raise not_found()
    result = int(raw.split("_")[1])
    if result > 9223372036854775807:
        raise not_found()
    return result


def permitted(card, role: str) -> list[str]:
    if role not in EDITORS or card.status in ("applied", "rejected"):
        return ["view"]
    actions = ["view", "postpone", "reject"]
    if not card.insufficient:
        actions.append("check" if card.action_level == "inspect_only" else "accept")
    if card.status == "accepted" and "accept" in actions:
        actions.remove("accept")
    return actions


def passport(conn, ws, rid: int) -> dict:
    cards = active_cards(conn, ws.id, include_decided=True)
    card = next((c for c in cards if c.rec_id == rid), None)
    if card is None:
        raise not_found()
    active = [c for c in cards if c.status in ("new", "accepted")]
    cutoff = conn.execute("SELECT max(data_cutoff) FROM audit_runs WHERE workspace_id = %s", (ws.id,)).fetchone()[0]
    _, overlaps = with_exposure(conn, active if card in active else [card], cutoff or today_msk())
    result = recommendation_item(card, overlaps[rid])
    row = conn.execute("""SELECT f.evidence, f.rule_version, f.safety_policy, f.candidate_level, f.policy_reasons,
                          (SELECT e.text FROM explanations e WHERE e.finding_id = f.id ORDER BY e.id DESC LIMIT 1)
                          FROM findings f WHERE f.id = %s""", (card.finding_id,)).fetchone()
    history = conn.execute("""SELECT type, created_at, actor_user_id, payload, finding_id FROM recommendation_events
                              WHERE recommendation_id = %s ORDER BY id""", (rid,)).fetchall()
    def actor(user):
        return "system" if user is None else {"user_id": ext("u", user)}
    decision = next((h for h in reversed(history) if h[0] in DECISIONS
                     and (h[0] != "accepted" or h[4] == card.finding_id)), None)
    allowed = permitted(card, ws.role)
    if result["action"] is None:
        allowed = [a for a in allowed if a not in ("accept", "check")]
    result.update({
        "postponed_until": decision[3].get("until") if decision and card.status == "postponed" else None,
        "allowed_actions": allowed,
        "blocked_actions": [] if ws.role in EDITORS else [{"action": a, "reason": "role_forbidden"}
                                                          for a in ("accept", "postpone", "reject", "check")],
        "explanation": {"text": row[5] or "Объяснение недоступно. Проверьте доказательства.", "source": "template"},
        "evidence": {"facts": {k: value(v) for k, v in row[0].items()},
                     "meta": {k: str(v) for k, v in card.meta.items()}, "rule_version": row[1]},
        "safety": {"safety_policy": row[2], "candidate_level": row[3], "policy_reasons": list(row[4]),
                   "data_status": card.lost.data_status},
        "limitations": ["Изменения выполняет клиент в рекламном кабинете",
                        "Подтверждение выполнения и замер результата в этом интерфейсе пока недоступны"],
        "execution": {"execution_mode": "manual" if card.action_level != "inspect_only" else "none",
                      "verification_status": None, "accepted_at": next(
                          (moment(h[1]) for h in reversed(history)
                           if h[0] == "accepted" and h[4] == card.finding_id), None),
                      "done_at": next((moment(h[1]) for h in reversed(history) if h[0] == "done"), None),
                      "before_state": None, "verification_checked_at": None},
        "decision": None if decision is None else {"event": DECISIONS[decision[0]], "at": moment(decision[1]),
                                                   "actor": actor(decision[2]), "reason": decision[3].get("reason"),
                                                   "comment": decision[3].get("comment")},
        "measurement": None,
        "history": [{"event": DECISIONS.get(h[0], h[0]), "at": moment(h[1]), "actor": actor(h[2])} for h in history],
    })
    return result


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["accept", "postpone", "reject", "check"]
    version_id: str = Field(pattern=r"^rv_[1-9][0-9]{0,18}$")
    until: date | None = None
    reason: Literal["wrong_data", "irrelevant_rule", "not_enough_context", "too_risky", "other"] | None = None
    comment: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def contextual_fields(self):
        if (self.until is not None) != (self.action == "postpone"):
            raise ValueError("until is required only for postpone")
        if self.action == "reject" and self.reason is None:
            raise ValueError("reject requires reason")
        if self.action != "reject" and (self.reason is not None or self.comment is not None):
            raise ValueError("reason and comment belong to reject")
        return self


@router.get("/workspaces/{workspace_id}/recommendations/{recommendation_id}")
def detail(conn: Conn, ws: CurrentWorkspace, recommendation_id: str):
    return passport(conn, ws, parse_id(recommendation_id, "rec"))


@router.post("/workspaces/{workspace_id}/recommendations/{recommendation_id}/actions")
def decide(conn: Conn, ws: CurrentWorkspace, recommendation_id: str, body: DecisionInput):
    rid = parse_id(recommendation_id, "rec")

    if conn.execute("SELECT id FROM recommendations WHERE id = %s FOR UPDATE", (rid,)).fetchone() is None:
        raise not_found()
    current = passport(conn, ws, rid)
    if ws.role not in EDITORS:
        raise ApiError(403, "forbidden_role")
    if current["version_id"] != body.version_id:
        raise ApiError(409, "stale_version", message="Рекомендация обновилась. Откройте текущую версию.")
    if body.action not in current["allowed_actions"]:
        raise ApiError(409, "action_unavailable", message="Действие недоступно для текущего состояния.")
    if body.until is not None and not today_msk() < body.until <= today_msk() + timedelta(days=365):
        raise ApiError(400, "invalid_request")
    payload = {k: v for k, v in body.model_dump(mode="json", exclude_none=True).items()
               if k in ("until", "reason", "comment")}
    finding = parse_id(body.version_id, "rv") if body.action in ("accept", "check") else None
    conn.execute("""INSERT INTO recommendation_events (recommendation_id, type, actor_user_id, finding_id, payload)
                    VALUES (%s, %s, %s, %s, %s)""",
                 (rid, EVENTS[body.action], ws.actor.user_id, finding, Jsonb(payload)))
    return passport(conn, ws, rid)
