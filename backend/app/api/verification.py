"""Durable requests for independent, read-only membership verification."""
import hashlib
import json
from datetime import datetime, timezone
from app.api.errors import ApiError
from app.audit.membership import METHOD, targets
from app.worker.guard import load_state
from app.worker.locks import workspace_shared, audit_exclusive


def status(conn, data, ws=None):
    done = next((e for e in reversed(data["events"]) if e[1] == "done"), None)
    base = {"method": METHOD, "proof_scope": "final_membership", "counted_in_saved_total": False}
    if done is None:
        return {**base, "status": "unavailable", "reason": "manual_execution_required", "can_request": False}
    if done[3] != data["finding"]:
        return {**base, "status": "unavailable", "reason": "execution_version_outdated", "can_request": False}
    row = conn.execute("""SELECT j.id,j.finished_at,j.last_error,r.status,r.reason,r.read_at,r.target_count,r.matched_count
        FROM recommendation_verification_jobs j LEFT JOIN LATERAL
        (SELECT status,reason,read_at,target_count,matched_count FROM recommendation_verification_reads
         WHERE job_id=j.id ORDER BY id DESC LIMIT 1) r ON true
        WHERE j.done_event_id=%s""", (done[0],)).fetchone()
    if row:
        jid, finished, error, state, reason, observed, total, matched = row
        return {**base, "request_id": f"verification_{jid}", "status": state if finished and state else "unavailable" if finished else "pending",
                "reason": reason if finished and reason else error or "queued", "can_request": False,
                "checked_at": observed.isoformat() if observed else None, "target_count": total, "matched_count": matched}
    capable = targets(data["action"]) is not None and data["current"]
    if ws is not None:
        access = load_state(conn,ws.id,data["account"],datetime.now(timezone.utc))
        capable = capable and ws.role in {"owner","admin","analyst","approver"} and access.workspace_status == "active" and access.has_analysis_access and access.direct_status == "connected" and access.direct_account_status == "active"
    return {**base, "status": "unavailable", "reason": "not_requested" if capable else "action_not_verifiable", "can_request": capable}


def enqueue(conn, ws, data, payload):
    if ws.role not in {"owner", "admin", "approver", "analyst"}:
        raise ApiError(403, "forbidden_role")
    workspace_shared(conn, ws.id)
    audit_exclusive(conn, ws.id)
    digest = hashlib.sha256(json.dumps({"operation": "verification", "recommendation_id": data["id"], "body": payload.model_dump(mode="json")}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    key = str(payload.idempotency_key)
    replay = conn.execute("SELECT id,requested_by,request_sha256 FROM recommendation_verification_jobs WHERE workspace_id=%s AND idempotency_key=%s", (ws.id,key)).fetchone()
    if replay:
        if replay[1:] != (ws.actor.user_id, digest):
            raise ApiError(409, "idempotency_conflict")
        return {"request_id": f"verification_{replay[0]}", "status": "queued"}
    if any(e[4].get("idempotency_key") == key for e in data["events"]):
        raise ApiError(409, "idempotency_conflict")
    if payload.expected_version_id != f"rv_{data['finding']}":
        raise ApiError(409, "version_outdated")
    if payload.expected_state_version != data["state"]:
        raise ApiError(409, "state_outdated")
    state = load_state(conn, ws.id, data["account"], datetime.now(timezone.utc))
    if state.workspace_status != "active" or not state.has_analysis_access:
        raise ApiError(403, "action_unavailable", reason="access_inactive")
    if state.direct_status != "connected" or state.direct_account_status != "active":
        raise ApiError(409, "action_unavailable", reason="direct_unavailable")
    if not status(conn, data)["can_request"]:
        raise ApiError(409, "action_unavailable", reason=status(conn,data)["reason"])
    done = next(e for e in reversed(data["events"]) if e[1] == "done")
    jid = conn.execute("""INSERT INTO recommendation_verification_jobs
        (workspace_id,recommendation_id,finding_id,done_event_id,requested_by,idempotency_key,request_sha256,method)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (ws.id,data["id"],done[3],done[0],ws.actor.user_id,key,digest,METHOD)).fetchone()[0]
    return {"request_id": f"verification_{jid}", "status": "queued"}
