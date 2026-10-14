"""GET /workspaces/{ws}/agents — команда AdPilot: Chief Analyst и специалисты из реестра (intelligence/agents).

Статус области считает agents/specialists.route по последнему аудиту workspace: какие правила запускались
(audit_runs.rules_run) и какие находки он дал. Модель статусы не выдумывает; изменения в кабинетах не выполняются."""

from datetime import timedelta

from fastapi import APIRouter

from app.api.deps import Conn, CurrentWorkspace
from app.intelligence.agents.registry import SPECIALISTS, get_agent
from app.intelligence.agents.specialists import route
from app.intelligence.contracts.evidence import EvidenceBundle
from app.rules.domain import windows

router = APIRouter()
LIMITATIONS = ("Изменения в рекламных кабинетах не выполняются",
               "Отраслевые нормы и обещания экономии без подтверждённых данных не используются",
               "«Не проверялось» означает, что правила области не запускались, а не что проблем нет")


def _goals(conn, ws: int, audit: int | None) -> dict:
    metrika = conn.execute("""SELECT EXISTS (SELECT 1 FROM metrika_connections
                              WHERE workspace_id = %s AND status = 'connected')""", (ws,)).fetchone()[0]
    selected = conn.execute("""SELECT coalesce(max(cardinality(c.goal_ids)) FILTER (WHERE c.is_selected), 0)
                               FROM metrika_counters c JOIN metrika_connections m ON m.id = c.metrika_connection_id
                               WHERE m.workspace_id = %s""", (ws,)).fetchone()[0]
    failure = None if audit is None else conn.execute(
        """SELECT s.source_failures->>'yandex_metrika' FROM audit_run_snapshots a JOIN snapshots s ON s.id = a.snapshot_id
           WHERE a.audit_run_id = %s AND s.source_failures ? 'yandex_metrika' ORDER BY s.id LIMIT 1""",
        (audit,)).fetchone()
    return {"metrika": "connected" if metrika else "missing", "selected_goals": selected,
            "source_failure": failure[0] if failure else None}


_PERIODS = """
SELECT r.campaign_id,
       sum(r.cost) FILTER (WHERE r.date BETWEEN %(b0)s AND %(b1)s), sum(r.clicks) FILTER (WHERE r.date BETWEEN %(b0)s AND %(b1)s),
       CASE WHEN bool_or(r.conversions IS NULL) FILTER (WHERE r.date BETWEEN %(b0)s AND %(b1)s) THEN NULL
            ELSE sum(r.conversions) FILTER (WHERE r.date BETWEEN %(b0)s AND %(b1)s) END,
       sum(r.cost) FILTER (WHERE r.date BETWEEN %(e0)s AND %(e1)s), sum(r.clicks) FILTER (WHERE r.date BETWEEN %(e0)s AND %(e1)s),
       CASE WHEN bool_or(r.conversions IS NULL) FILTER (WHERE r.date BETWEEN %(e0)s AND %(e1)s) THEN NULL
            ELSE sum(r.conversions) FILTER (WHERE r.date BETWEEN %(e0)s AND %(e1)s) END
FROM stat_rows r WHERE r.snapshot_id = %(snapshot)s AND r.level = 'campaign' AND r.campaign_id = ANY(%(campaigns)s)
GROUP BY r.campaign_id ORDER BY r.campaign_id"""


def _campaign_periods(conn, audit: int) -> tuple[dict, ...]:
    """Кампании с находкой высокого CPA в последнем аудите: база (30 дней) и окно (7 завершённых дней) из снимка —
    те же окна, что у правил, но по дням до partial_from, чтобы досчёт конверсий не исказил CR."""
    facts = []
    rows = conn.execute("""SELECT a.snapshot_id, s.partial_from, array_agg(DISTINCT i.object_id)
                           FROM findings f JOIN issues i ON i.id = f.issue_id
                           JOIN audit_run_snapshots a ON a.audit_run_id = f.audit_run_id
                                                     AND a.direct_account_id = i.direct_account_id
                           JOIN snapshots s ON s.id = a.snapshot_id
                           WHERE f.audit_run_id = %s AND i.issue_type = 'high_cpa' AND i.object_type = 'campaign'
                           GROUP BY a.snapshot_id, s.partial_from""", (audit,)).fetchall()
    for snapshot, partial_from, campaigns in rows:
        evaluation, baseline = windows(partial_from - timedelta(1))
        params = {"snapshot": snapshot, "campaigns": list(campaigns), "b0": baseline.date_from,
                  "b1": baseline.date_to, "e0": evaluation.date_from, "e1": evaluation.date_to}
        for campaign, *v in conn.execute(_PERIODS, params).fetchall():
            if v[0] is None or v[3] is None:
                continue  # нет строк в одном из окон — сравнивать не с чем
            facts.append({"id": f"p{snapshot}_{campaign}", "kind": "campaign_periods", "object": campaign,
                          "values": dict(zip(("before_cost", "before_clicks", "before_conversions", "after_cost",
                                              "after_clicks", "after_conversions"), v))})
    return tuple(facts)


def _bundle(conn, ws: int) -> EvidenceBundle:
    last = conn.execute("""SELECT id, rules_run FROM audit_runs WHERE workspace_id = %s
                           ORDER BY created_at DESC, id DESC LIMIT 1""", (ws,)).fetchone()
    goals = _goals(conn, ws, last[0] if last else None)
    missing = ([] if last else ["source_missing"]) + ([] if goals["metrika"] == "connected" else ["metrika_missing"])
    health = {"rules_run": list(last[1]) if last else [], "missing": missing, "goals": goals}
    if last is None:
        health["data_sufficiency"] = "insufficient"
    findings = () if last is None else tuple(
        {"id": f"f{fid}", "rule": rule} for fid, rule in conn.execute(
            "SELECT id, rule_version FROM findings WHERE audit_run_id = %s ORDER BY id", (last[0],)).fetchall())
    facts = () if last is None else _campaign_periods(conn, last[0])
    return EvidenceBundle(facts=facts, findings=findings, metrics=(), constraints=(), data_health=health,
                          capabilities={}, period={}, source_registry={})


@router.get("/workspaces/{workspace_id}/agents")
def agents(conn: Conn, ws: CurrentWorkspace):
    reports = {r.agent_id: r for r in route(_bundle(conn, ws.id))}
    chief = get_agent("chief_analyst")
    return {"mode": "recommendations_only",
            "coordinator": {"id": chief.agent_id, "name": chief.name, "enabled": chief.enabled},
            "specialists": [{"id": s.agent_id, "name": s.name, "domain": s.domain,
                             "status": reports[s.agent_id].status.value,
                             "findings": len(reports[s.agent_id].finding_ids),
                             "missing_data": list(reports[s.agent_id].missing)} for s in SPECIALISTS],
            "limitations": list(LIMITATIONS)}
