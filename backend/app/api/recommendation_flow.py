"""Schema-native manual decisions. No advertising writes or synthetic verification."""

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import Field
from psycopg.types.json import Jsonb

from app.api.active import status_of, today_msk
from app.api.deps import Conn, CurrentWorkspace
from app.api.errors import ApiError, not_found
from app.api.routes import Strict
from app.api.serialize import action, ext, moment, value
from app.audit.present import title
from app.worker.guard import load_state
from app.worker.locks import audit_exclusive, workspace_shared

router = APIRouter()
PREFIX = "/workspaces/{workspace_id}/recommendations/{rec_id}"
DECIDERS = {"owner", "admin", "approver", "analyst"}
REASONS = Literal["wrong_data", "irrelevant_rule", "not_enough_context", "too_risky", "other"]


class Mutation(Strict):
    expected_version_id: str = Field(pattern=r"^rv_[1-9][0-9]{0,18}$")
    expected_state_version: str = Field(pattern=r"^(initial|ev_[1-9][0-9]{0,18})$")
    idempotency_key: UUID


class Decision(Mutation):
    action: Literal["reject", "postpone", "check"]
    reason: REASONS | None = None
    comment: str | None = Field(default=None, max_length=500)
    until: date | None = None


def _number(rec_id: str) -> int:
    if not re.fullmatch(r"rec_[1-9][0-9]{0,18}", rec_id) or int(rec_id[4:]) > 2**63 - 1:
        raise not_found()
    return int(rec_id[4:])


def _load(conn, ws, rec_id):
    rid = _number(rec_id)
    row = conn.execute("""SELECT r.id, r.issue_id, i.issue_type, i.object_type, i.object_id, i.closed_at,
                                i.direct_account_id, coalesce(da.client_login, dc.yandex_login), da.is_selected,
                                coalesce(e.finding_id, r.finding_id), coalesce(e.explanation_id, r.explanation_id)
                         FROM recommendations r JOIN issues i ON i.id = r.issue_id
                         JOIN direct_accounts da ON da.id = i.direct_account_id
                         JOIN direct_connections dc ON dc.id = da.direct_connection_id
                         LEFT JOIN LATERAL (SELECT finding_id, explanation_id FROM recommendation_events
                           WHERE recommendation_id = r.id AND type = 'seen_again' ORDER BY id DESC LIMIT 1) e ON true
                         WHERE r.id = %s AND i.workspace_id = %s""", (rid, ws.id)).fetchone()
    if row is None:
        raise not_found()
    keys = ("id", "issue", "topic", "object_type", "object_id", "closed", "account", "login", "selected",
            "finding", "explanation")
    data = dict(zip(keys, row))
    f = conn.execute("""SELECT action_level, action, evidence, evidence_meta, lost, recoverable, rule_version,
                              safety_policy, policy_reasons, audit_run_id, created_at FROM findings WHERE id = %s""",
                     (data["finding"],)).fetchone()
    data.update(zip(("level", "action", "evidence", "meta", "lost", "recoverable", "rule", "policy",
                     "policy_reasons", "audit", "computed_at"), f))
    data["events"] = conn.execute("""SELECT id, type, actor_user_id, finding_id, payload, created_at
                                      FROM recommendation_events WHERE recommendation_id = %s ORDER BY id""",
                                  (rid,)).fetchall()
    last = next((e for e in reversed(data["events"]) if e[1] not in ("seen_again", "measurement_skipped")), None)
    data["status"] = "resolved" if data["closed"] and (not last or last[1] != "measured") else status_of(last[1] if last else None,
                                       last[4].get("until") if last else None, today_msk())
    data["state"] = ext("ev", data["events"][-1][0]) if data["events"] else "initial"
    data["execution"] = next((e[1] for e in reversed(data["events"]) if e[1] in ("done", "checked")), None)
    latest = conn.execute("SELECT id FROM audit_runs WHERE workspace_id = %s ORDER BY created_at DESC, id DESC LIMIT 1",
                          (ws.id,)).fetchone()
    data["current"] = bool(latest and latest[0] == data["audit"] and data["selected"])
    return data


def _available(conn, ws, data):
    state = load_state(conn, ws.id, None, datetime.now(timezone.utc))
    if ws.role not in DECIDERS:
        return [], "role_forbidden"
    if state.workspace_status != "active" or not state.paid:
        return [], "access_inactive"
    if data["status"] not in ("new", "postponed"):
        return [], "already_decided"
    if not data["current"]:
        return [], "evidence_not_current"
    if action(data["action"], data["meta"] or {}, data["level"], data["topic"]) is None:
        return [], "action_unavailable"
    return (["check", "postpone"] if data["level"] == "inspect_only"
            else ["mark_done_manually", "postpone", "reject"]), None


def _measurement(conn, data):
    row = conn.execute("""SELECT id, policy, before_from, before_to, after_from, after_to FROM measurements
                          WHERE recommendation_id = %s ORDER BY id DESC LIMIT 1""", (data["id"],)).fetchone()
    if row is None:
        return None
    mid, policy, bf, bt, af, at = row
    r = conn.execute("""SELECT verdict, before, after, saved, effect, created_at FROM recommendation_results
                        WHERE measurement_id = %s""", (mid,)).fetchone()
    skipped = any(e[1] == "measurement_skipped" for e in data["events"])
    result = None if not r else {"verdict": r[0], "before": {k: value(v) for k, v in r[1].items()},
                                "after": {k: value(v) for k, v in r[2].items()},
                                "saved": value(r[3]) if r[3] else None, "effect": r[4],
                                "computed_at": moment(r[5]), "counted_in_saved_total": False}
    # shortcut: no persisted verification exists in this schema; never count unconfirmed savings.
    return {"id": ext("measurement", mid), "policy": policy,
            "before_period": {"from": bf.isoformat(), "to": bt.isoformat()},
            "after_period": {"from": af.isoformat(), "to": at.isoformat()},
            "status": "complete" if r else "skipped" if skipped else "pending", "result": result}


def _passport(conn, ws, data):
    allowed, blocked = _available(conn, ws, data)
    explanation = conn.execute("SELECT text, source FROM explanations WHERE id = %s", (data["explanation"],)).fetchone()
    manual = data["execution"] == "done"
    return {"id": ext("rec", data["id"]), "version_id": ext("rv", data["finding"]),
            "state_version": data["state"], "status": data["status"],
            "title": title(data["topic"], data["object_type"], data["object_id"], data["meta"] or {}),
            "ad_account": {"id": ext("acc", data["account"]), "login": data["login"]},
            "object": {"type": data["object_type"], "id": str(data["object_id"]), "name": None},
            "action_level": data["level"], "action": action(data["action"], data["meta"] or {}, data["level"], data["topic"]),
            "execution_mode": "manual" if manual else "none" if data["execution"] == "checked" else None,
            "verification_status": "pending" if manual else "not_required" if data["execution"] == "checked" else None,
            "verification": {"status": "unavailable", "reason": "verification_worker_not_implemented"},
            "evidence_current": data["current"], "exposure": value(data["lost"]), "can_save": value(data["recoverable"]),
            "evidence": {k: value(v) for k, v in data["evidence"].items()},
            "rule_version": data["rule"], "safety_policy": data["policy"], "policy_reasons": data["policy_reasons"],
            "computed_at": moment(data["computed_at"]),
            "explanation": {"text": explanation[0], "source": explanation[1]} if explanation else None,
            "history": [{"id": ext("ev", e[0]), "type": e[1], "actor_id": ext("u", e[2]) if e[2] else None,
                         "version_id": ext("rv", e[3]) if e[3] else None, "created_at": moment(e[5]),
                         "reason": e[4].get("reason"), "comment": e[4].get("comment"), "until": e[4].get("until")}
                        for e in data["events"]],
            "latest_measurement": _measurement(conn, data), "allowed_actions": allowed,
            "blocked_actions": [{"reason": blocked}] if blocked else []}


@router.get(PREFIX)
def passport(rec_id: str, conn: Conn, ws: CurrentWorkspace):
    return _passport(conn, ws, _load(conn, ws, rec_id))


def _prepare(conn, ws, rec_id, payload, operation):
    if ws.role not in DECIDERS:
        raise ApiError(403, "forbidden_role")
    workspace_shared(conn, ws.id)
    audit_exclusive(conn, ws.id)
    data = _load(conn, ws, rec_id)
    digest = hashlib.sha256(json.dumps({"operation": operation, "body": payload.model_dump(mode="json")},
                                      sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    for event in data["events"]:
        if event[4].get("idempotency_key") == str(payload.idempotency_key):
            if event[2] != ws.actor.user_id or event[4].get("request_sha256") != digest:
                raise ApiError(409, "idempotency_conflict", message="Ключ уже использован для другого запроса.")
            return data, digest, event
    if payload.expected_version_id != ext("rv", data["finding"]):
        raise ApiError(409, "version_outdated", message="Рекомендация обновлена. Откройте её заново.")
    if payload.expected_state_version != data["state"]:
        raise ApiError(409, "state_outdated", message="Решение уже изменилось. Откройте рекомендацию заново.")
    allowed, blocked = _available(conn, ws, data)
    if operation not in allowed:
        raise ApiError(409 if blocked != "access_inactive" else 403, "action_unavailable", reason=blocked,
                       message="Действие недоступно в текущем состоянии.")
    return data, digest, None


def _record(conn, ws, data, payload, digest, kind, extra):
    body = {"idempotency_key": str(payload.idempotency_key), "request_sha256": digest, "version_id": ext("rv", data["finding"]), **extra}
    finding = data["finding"] if kind in ("done", "checked") else None
    execution = today_msk() if kind == "done" else None
    event = conn.execute("""INSERT INTO recommendation_events
                    (recommendation_id, type, actor_user_id, finding_id, payload, execution_date)
                    VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, type, actor_user_id, finding_id, payload, created_at""",
                 (data["id"], kind, ws.actor.user_id, finding, Jsonb(body), execution)).fetchone()
    return _receipt(data, event)


def _receipt(data, event):
    kind = event[1]
    return {"recommendation_id": ext("rec", data["id"]), "event_id": ext("ev", event[0]),
            "version_id": event[4]["version_id"], "state_version": ext("ev", event[0]),
            "status": {"done": "applied", "checked": "applied", "rejected": "rejected", "postponed": "postponed"}[kind],
            "execution_mode": "manual" if kind == "done" else "none" if kind == "checked" else None,
            "verification_status": "pending" if kind == "done" else "not_required" if kind == "checked" else None}


@router.post(PREFIX + "/decisions")
def decide(rec_id: str, payload: Decision, conn: Conn, ws: CurrentWorkspace):
    if payload.action == "reject":
        if payload.reason is None or (payload.reason == "other" and not (payload.comment or "").strip()) or payload.until:
            raise ApiError(400, "invalid_request")
    elif payload.reason is not None or payload.comment is not None:
        raise ApiError(400, "invalid_request")
    if payload.action != "postpone" and payload.until is not None:
        raise ApiError(400, "invalid_request")
    data, digest, replay = _prepare(conn, ws, rec_id, payload, payload.action)
    if replay:
        return _receipt(data, replay)
    if payload.action == "postpone":
        if payload.until is None or not today_msk() < payload.until <= today_msk() + timedelta(days=90):
            raise ApiError(400, "invalid_request")
    extra = {k: v for k, v in payload.model_dump(mode="json").items() if k in ("reason", "comment", "until") and v is not None}
    return _record(conn, ws, data, payload, digest, {"reject": "rejected", "postpone": "postponed", "check": "checked"}[payload.action], extra)


@router.post(PREFIX + "/manual-execution")
def manual_execution(rec_id: str, payload: Mutation, conn: Conn, ws: CurrentWorkspace):
    data, digest, replay = _prepare(conn, ws, rec_id, payload, "mark_done_manually")
    if replay:
        return _receipt(data, replay)
    return _record(conn, ws, data, payload, digest, "done", {"execution_mode": "manual", "verification_status": "pending"})


@router.post(PREFIX + "/verification")
def verification(rec_id: str, payload: Mutation, conn: Conn, ws: CurrentWorkspace):
    if ws.role not in DECIDERS:
        raise ApiError(403, "forbidden_role")
    data = _load(conn, ws, rec_id)
    if payload.expected_version_id != ext("rv", data["finding"]) or payload.expected_state_version != data["state"]:
        raise ApiError(409, "version_outdated", message="Рекомендация обновлена. Откройте её заново.")
    raise ApiError(503, "verification_unavailable", reason="verification_worker_not_implemented",
                   message="Сверка по данным Директа пока недоступна. Ручное действие не подтверждено.")
