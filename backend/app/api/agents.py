"""GET /workspaces/{ws}/agents — команда AdPilot: Chief Analyst и специалисты из реестра (intelligence/agents).

Статус области считает agents/specialists.route по последнему аудиту workspace: какие правила запускались
(audit_runs.rules_run) и какие находки он дал. Модель статусы не выдумывает; изменения в кабинетах не выполняются."""

from fastapi import APIRouter

from app.api.deps import Conn, CurrentWorkspace
from app.intelligence.agents.registry import SPECIALISTS, get_agent
from app.intelligence.agents.specialists import route
from app.intelligence.contracts.evidence import EvidenceBundle

router = APIRouter()
LIMITATIONS = ("Изменения в рекламных кабинетах не выполняются",
               "Отраслевые нормы и обещания экономии без подтверждённых данных не используются",
               "«Не проверялось» означает, что правила области не запускались, а не что проблем нет")


def _bundle(conn, ws: int) -> EvidenceBundle:
    last = conn.execute("""SELECT id, rules_run FROM audit_runs WHERE workspace_id = %s
                           ORDER BY created_at DESC, id DESC LIMIT 1""", (ws,)).fetchone()
    metrika = conn.execute("""SELECT EXISTS (SELECT 1 FROM metrika_connections
                              WHERE workspace_id = %s AND status = 'connected')""", (ws,)).fetchone()[0]
    missing = ([] if last else ["source_missing"]) + ([] if metrika else ["metrika_missing"])
    health = {"rules_run": list(last[1]) if last else [], "missing": missing}
    if last is None:
        health["data_sufficiency"] = "insufficient"
    findings = () if last is None else tuple(
        {"id": f"f{fid}", "rule": rule} for fid, rule in conn.execute(
            "SELECT id, rule_version FROM findings WHERE audit_run_id = %s ORDER BY id", (last[0],)).fetchall())
    return EvidenceBundle(facts=(), findings=findings, metrics=(), constraints=(), data_health=health,
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
