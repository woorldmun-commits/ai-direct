"""Паспорт рекомендации (API_CONTRACT.md §5) — проблема, доказательства, действие, решение, история — и
allowed_actions (§4). Только чтение, всё — в RLS-контексте workspace запроса.

Текущая версия — последний seen_again или исходный вывод. Если рекомендация активна (app/api/active.py), числа,
уровень и exposure_overlap — как у карточки в списке и «Сегодня» (одно определение); у неактивной — как сохранил
аудит, exposure_overlap = null (в разложении exposure_total она не участвует).
Статус — из последнего события решения (active.status_of). Событий accepted / viewed в схеме нет: requires_decision и
accepted не выдаются, accept недоступен."""

from dataclasses import dataclass
from datetime import date, datetime

import psycopg

from app.api.active import Card, active_cards, status_of, today_msk, with_exposure
from app.api.serialize import action, ext, moment, value, value_of
from app.audit.present import title
from app.contract import Value
from app.worker.measure import verification_status

DECIDERS = frozenset({"owner", "admin", "approver", "analyst"})
HUMAN = ("postponed", "rejected", "done", "checked")
HISTORY_NAMES = {"done": "manual_claimed", "checked": "recommendation_checked"}

_REC = """
SELECT r.id, r.created_at, i.closed_at, i.issue_type, i.object_type, i.object_id, i.direct_account_id,
       coalesce(da.client_login, dc.yandex_login), coalesce(s.finding_id, r.finding_id),
       coalesce(s.explanation_id, r.explanation_id)
FROM recommendations r
JOIN issues i ON i.id = r.issue_id AND i.workspace_id = %(ws)s
JOIN direct_accounts da ON da.id = i.direct_account_id
JOIN direct_connections dc ON dc.id = da.direct_connection_id
LEFT JOIN LATERAL (SELECT e.finding_id, e.explanation_id FROM recommendation_events e
                   WHERE e.recommendation_id = r.id AND e.type = 'seen_again' ORDER BY e.id DESC LIMIT 1) s ON true
WHERE r.id = %(rec)s
"""
_FINDING = """SELECT lost, recoverable, evidence, evidence_meta, action, safety_policy, candidate_level, action_level,
                     policy_reasons, rule_version, created_at FROM findings WHERE id = %s"""


@dataclass(frozen=True)
class State:
    """То, что нужно и паспорту, и проверке действия."""
    rec_id: int
    finding_id: int
    status: str
    closed: bool
    level: str      # уровень для человека (у удержанной «недостаточно данных» — inspect_only)
    db_level: str   # уровень сохранённого вывода: его проверяет триггер БД на done / checked
    last_human: tuple | None  # (id, type, payload, actor, created_at) последнего решения человека
    until: str | None


def _events(conn: psycopg.Connection, rec: int) -> list[tuple]:
    return conn.execute("""SELECT id, type, payload, actor_user_id, created_at FROM recommendation_events
                           WHERE recommendation_id = %s ORDER BY id""", (rec,)).fetchall()


def load(conn: psycopg.Connection, ws: int, rec: int, today: date | None = None) -> tuple[State, dict] | None:
    today = today or today_msk()
    row = conn.execute(_REC, {"ws": ws, "rec": rec}).fetchone()
    if row is None:
        return None
    (rec, created, closed, issue_type, object_type, object_id, account, login, finding, explanation) = row
    f = conn.execute(_FINDING, (finding,)).fetchone()
    events = _events(conn, rec)
    decided = [e for e in events if e[1] not in ("seen_again", "measurement_skipped")]
    last = decided[-1] if decided else None
    until = (last[2] or {}).get("until") if last and last[1] == "postponed" else None
    status = status_of(last[1] if last else None, until, today)
    human = [e for e in events if e[1] in HUMAN]
    cards = active_cards(conn, ws, today=today)
    card = next((c for c in cards if c.rec_id == rec), None)
    state = State(rec, finding, status, closed is not None, card.action_level if card else f[7], f[7],
                  human[-1] if human else None, until)
    raw = {"created": created, "issue_type": issue_type, "object_type": object_type, "object_id": object_id,
           "account": account, "login": login, "finding": f, "explanation": explanation, "events": events,
           "card": card, "cards": cards}
    return state, raw


def allowed(state: State, role: str) -> tuple[list[str], list[dict]]:
    """allowed_actions / blocked_actions (§4): из роли, статуса и уровня действия. accept — нет событий в схеме."""
    if state.closed or state.status not in ("new", "requires_decision", "postponed"):
        possible = []
    elif state.level == "inspect_only":
        possible = (["check"] if state.db_level == "inspect_only" else []) + ["postpone"]
    else:
        possible = ["mark_done_manually", "postpone", "reject"]
    if role not in DECIDERS:
        return [], [{"action": a, "reason": "role_forbidden"} for a in possible]
    return possible, []


def _actor(user_id: int | None):
    return "system" if user_id is None else {"user_id": ext("u", user_id), "name": None}


def _history(raw: dict) -> list[dict]:
    out = [{"event": "created", "at": moment(raw["created"]), "actor": "system"}]
    out += [{"event": HISTORY_NAMES.get(t, t), "at": moment(at), "actor": _actor(user)}
            for _, t, _, user, at in raw["events"]]
    return out


def _decision(state: State) -> dict | None:
    if state.last_human is None:
        return None
    _, kind, payload, user, at = state.last_human
    out = {"event": HISTORY_NAMES.get(kind, kind), "at": moment(at), "actor": _actor(user)}
    if kind == "rejected":
        out |= {"reason": payload.get("reason"), "comment": payload.get("comment")}
    if kind == "postponed":
        out["until"] = payload.get("until")
    return out


def _execution(conn: psycopg.Connection, state: State) -> dict:
    out = {"execution_mode": None, "verification_status": None, "accepted_at": None, "done_at": None,
           "before_state": None, "verification_checked_at": None}
    if state.last_human and state.status == "applied":
        event_id, kind, _, _, at = state.last_human
        if kind == "done":
            out |= {"execution_mode": "manual", "done_at": moment(at),
                    "verification_status": verification_status(conn, state.rec_id, event_id)}
        elif kind == "checked":
            out |= {"execution_mode": "none", "verification_status": "not_required", "done_at": moment(at)}
    return out


def _numbers(conn: psycopg.Connection, ws: int, raw: dict, card: Card | None) -> tuple[Value, Value, dict | None]:
    f = raw["finding"]
    if card is None:
        return Value.from_stored(f[0]), Value.from_stored(f[1]), None
    cards = raw["cards"]
    cutoff = conn.execute("SELECT max(data_cutoff) FROM audit_runs WHERE workspace_id = %s", (ws,)).fetchone()[0]
    _, overlaps = with_exposure(conn, cards, cutoff or today_msk())
    return card.lost, card.recoverable, value_of(overlaps[card.rec_id])


def render(conn: psycopg.Connection, ws: int, role: str, state: State, raw: dict) -> dict:
    f, card = raw["finding"], raw["card"]
    lost, recoverable, overlap = _numbers(conn, ws, raw, card)
    meta = f[3] or {}
    text, source = conn.execute("SELECT text, source FROM explanations WHERE id = %s",
                                (raw["explanation"],)).fetchone()
    can, blocked = allowed(state, role)
    return {"id": ext("rec", state.rec_id), "version_id": ext("rv", state.finding_id),
            "title": title(raw["issue_type"], raw["object_type"], raw["object_id"], meta,
                           insufficient=bool(card and card.insufficient)),
            "ad_account": {"id": ext("acc", raw["account"]), "login": raw["login"]},
            "object": {"type": raw["object_type"], "id": str(raw["object_id"]), "name": None},
            "status": state.status, "postponed_until": state.until if state.status == "postponed" else None,
            "action_level": state.level, "allowed_actions": can, "blocked_actions": blocked,
            "exposure": value_of(lost), "exposure_overlap": overlap, "can_save": value_of(recoverable),
            "data_status": lost.data_status, "data_sufficiency": lost.data_sufficiency,
            "period": {"from": lost.period_from.isoformat(), "to": lost.period_to.isoformat()},
            "explanation": {"text": text, "source": source},
            "action": action(f[4], meta, state.level, raw["issue_type"]), "candidate_action": f[4],
            "evidence": {"facts": {k: value(v) for k, v in (f[2] or {}).items()}, "meta": meta,
                         "rule_version": f[9]},
            "safety": {"safety_policy": f[5], "candidate_level": f[6], "policy_reasons": list(f[8] or ()),
                       "data_status": lost.data_status},
            "limitations": list(f[8] or ()), "execution": _execution(conn, state), "decision": _decision(state),
            "measurement": None, "history": _history(raw), "computed_at": moment(f[10]),
            "created_at": moment(raw["created"])}


def passport(conn: psycopg.Connection, ws: int, role: str, rec: int, now: datetime | None = None) -> dict | None:
    loaded = load(conn, ws, rec, today_msk(now))
    return None if loaded is None else render(conn, ws, role, *loaded)
