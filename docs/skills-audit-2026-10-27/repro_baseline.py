"""Mock-only reproduction: a metrics request persists an unread baseline UUID."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.api import intelligence as m
from app.api.deps import Workspace, Actor
from app.intelligence.tools import ToolContext

main_id, unchecked_id = uuid4(), uuid4()
data = dict(data_mode="synthetic", period_start="2026-10-01", period_end="2026-10-08", currency="RUB", timezone="Europe/Moscow", attribution_model="last", attribution_window="30d", conversion_definition="lead", cost_definition="excluding_vat", account_ids=[], values={"cost":"100", "clicks":"10", "conversions":"2"})


class Conn:
    def __init__(self):
        self.inserts = []

    def execute(self, sql, args):
        if sql.startswith("INSERT INTO intelligence_runs"):
            self.inserts.append(args)
        return self

    def fetchone(self):
        return None


conn = Conn()
ws = Workspace(1, "owner", Actor(7))
request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(intelligence_enabled=True))))
context = ToolContext(actor_id=7, workspace_id=1, allowed_accounts=frozenset(), request_id="repro", run_id="repro", deadline=datetime.now(timezone.utc)+timedelta(seconds=60), permissions=frozenset({"metrics.read","analysis.run"}))
body = m.AnalysisRequest(question="metrics", import_id=main_id, before_import_id=unchecked_id, idempotency_key=uuid4())
with patch.object(m,"_profile",return_value={"revision":1,"fields":{"conversion_definition":"lead"}}), patch.object(m,"_import",return_value=(data,datetime.now(timezone.utc))) as imported, patch.object(m,"_tool_context",return_value=context):
    result = m.analyze(body,request,conn,ws)
    assert imported.call_count == 1
    assert imported.call_args.args[2] == main_id
    assert conn.inserts[0][3] == unchecked_id
    print("metrics analyze returned:",result["status"])
    print("source reads:",imported.call_count,"; unchecked baseline persisted:",conn.inserts[0][3] == unchecked_id)
