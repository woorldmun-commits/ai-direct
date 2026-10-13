"""GET /workspaces/{ws}/recommendations/{id} — паспорт; POST …/{id}/actions — решение человека (API_CONTRACT.md §4, §6).
Ни одно действие не обращается к Директу. Событие рекомендации и событие outbox — одна транзакция (ARCHITECTURE §5.1).

Проверки POST по порядку §6: (1) workspace → 404; (2) формат → 400; (3) version_id не последний → 409
version_outdated + актуальная рекомендация; (4) переход из текущего status → 409 invalid_transition (повтор того же
решения — 200 без новой записи); (5) действие в allowed_actions → иначе 403 forbidden_role / 422 action_unavailable.
Параллельные запросы по одной рекомендации — под advisory-блокировкой транзакции (двойной клик не пишет дважды).

Действие → событие: mark_done_manually → done (execution_date — день по поясу данных, worker/measure.py),
check → checked, postpone → postponed {until}, reject → rejected {reason, comment}. view — без записи (событий
просмотра в схеме нет). accept — 422 action_unavailable: события accepted и before_state в схеме нет."""

import re
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.active import today_msk
from app.api.deps import Conn, CurrentWorkspace
from app.api.errors import ApiError, error_body, not_found
from app.api.passport import allowed, load, passport, render
from app.worker.measure import execution_date
from app.worker.outbox import emit

router = APIRouter()

_REC = re.compile(r"rec_([1-9][0-9]{0,18})")
EVENT = {"mark_done_manually": "done", "check": "checked", "postpone": "postponed", "reject": "rejected"}
REASONS = Literal["wrong_data", "irrelevant_rule", "not_enough_context", "too_risky", "other"]
MAX_POSTPONE = 90


class ActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["view", "accept", "mark_done_manually", "check", "postpone", "reject"]
    version_id: Annotated[str, Field(pattern=r"^rv_[1-9][0-9]{0,18}$")]
    until: date | None = None
    reason: REASONS | None = None
    comment: Annotated[str | None, Field(max_length=500)] = None

    @model_validator(mode="after")
    def _shape(self):
        if (self.action == "postpone") != (self.until is not None):
            raise ValueError("until — только и обязательно для postpone")
        if (self.action == "reject") != (self.reason is not None):
            raise ValueError("reason — только и обязательно для reject")
        if self.comment is not None and self.action != "reject":
            raise ValueError("comment — только для reject")
        if self.reason == "other" and not (self.comment or "").strip():
            raise ValueError("other без comment")
        return self


def _rec_id(value: str) -> int:
    m = _REC.fullmatch(value)
    if not m or int(m.group(1)) > 2**63 - 1:
        raise not_found()
    return int(m.group(1))


@router.get("/workspaces/{workspace_id}/recommendations/{recommendation_id}")
def get_recommendation(conn: Conn, ws: CurrentWorkspace, recommendation_id: Annotated[str, Path()]):
    out = passport(conn, ws.id, ws.role, _rec_id(recommendation_id))
    if out is None:
        raise not_found()
    return out


def _check_until(until: date, now: datetime) -> None:
    today = today_msk(now)
    if not today + timedelta(days=1) <= until <= today + timedelta(days=MAX_POSTPONE):
        raise ApiError(400, "invalid_request", "until_out_of_range")


def _is_repeat(state, body: ActionBody) -> bool:
    """Решение уже стало текущим состоянием (двойной клик) — 200 без новой записи."""
    if state.last_human is None or state.last_human[1] != EVENT.get(body.action):
        return False
    if body.action == "postpone":
        return state.status == "postponed" and state.until == body.until.isoformat()
    return state.status in ("rejected", "applied")


def _record(conn, ws: int, user: int, state, body: ActionBody, now: datetime) -> None:
    kind = EVENT[body.action]
    payload = {"until": body.until.isoformat()} if kind == "postponed" else {}
    if kind == "rejected":
        payload = {"reason": body.reason, **({"comment": body.comment} if body.comment else {})}
    conn.execute("""INSERT INTO recommendation_events (recommendation_id, type, actor_user_id, finding_id, payload,
                                                       execution_date, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                 (state.rec_id, kind, user, state.finding_id if kind in ("done", "checked") else None,
                  Jsonb(payload), execution_date(now) if kind == "done" else None, now))
    emit(conn, ws, f"recommendation_{kind}", "recommendation", state.rec_id, {"finding_id": state.finding_id})


@router.post("/workspaces/{workspace_id}/recommendations/{recommendation_id}/actions")
def act(request: Request, conn: Conn, ws: CurrentWorkspace, body: ActionBody,
        recommendation_id: Annotated[str, Path()]):
    rec, now = _rec_id(recommendation_id), datetime.now(timezone.utc)
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"recommendation:{rec}",))
    loaded = load(conn, ws.id, rec, today_msk(now))
    if loaded is None:
        raise not_found()
    state, raw = loaded
    if body.until is not None:
        _check_until(body.until, now)
    if body.action != "view" and body.version_id != f"rv_{state.finding_id}":
        current = render(conn, ws.id, ws.role, state, raw)
        return JSONResponse({**error_body("version_outdated", request.scope["state"]["request_id"]),
                             "recommendation": current}, status_code=409)
    if body.action == "view" or _is_repeat(state, body):
        return render(conn, ws.id, ws.role, state, raw)
    if state.closed or state.status not in ("new", "requires_decision", "postponed"):
        raise ApiError(409, "invalid_transition")
    _authorize(ws.role, state, body.action)
    _record(conn, ws.id, ws.actor.user_id, state, body, now)
    return passport(conn, ws.id, ws.role, rec, now)


def _authorize(role: str, state, action: str) -> None:
    can, blocked = allowed(state, role)
    if action in can:
        return
    if any(b["action"] == action for b in blocked):
        raise ApiError(403, "forbidden_role")
    raise ApiError(422, "action_unavailable", "accept_unavailable" if action == "accept" else "action_level")

