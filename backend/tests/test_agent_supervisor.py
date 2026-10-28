"""Synthetic fixtures only: never evidence of a live customer result."""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import pytest
from pydantic import ValidationError
from app.agents.supervisor import Evidence, Manifest, Submission, verify
from app.agents.__main__ import MAX_BYTES, load
NOW = datetime(2026,10,18,12,tzinfo=timezone.utc)
RECORD = {"id":"e1","workspace_id":1,"metric":"cost","source_id":"record_1",
 "source_version":"snapshot@1","source_sha256":"a"*64,"captured_at":"2026-10-18T11:59:00Z",
 "value":{"amount":"100.00","unit":"rub","source":"yandex_direct",
 "period_from":"2026-10-16","period_to":"2026-10-17","calculation_type":"actual",
 "data_status":"complete","data_sufficiency":"sufficient","snapshot_id":1}}

def manifest(record=None):
 return {"schema_version":1,"synthetic":True,"workspace_id":1,"period_from":"2026-10-16",
 "period_to":"2026-10-17","max_age_seconds":3600,"evidence":[record or copy.deepcopy(RECORD)]}

def check(record=None,trusted=None):
 return verify(Submission.model_validate({"schema_version":1,"synthetic":True,
 "claims":[record or copy.deepcopy(RECORD)]}),Manifest.model_validate(trusted or manifest()),now=NOW)

@pytest.mark.parametrize('field,bad',[
 ('id',' bad id '),('id','x'*101),('id','valid\n'),
 ('metric','prefix metric suffix'),('source_version','bad/version'),
 ('source_sha256','PREFIX'+'a'*64+'SUFFIX'),('source_sha256','a'*64+'\n'),
 ('source_sha256','A'*64),
])
def test_identifiers_and_hashes_are_canonical(field,bad):
 record=copy.deepcopy(RECORD)
 record[field]=bad
 with pytest.raises(ValidationError):
     Evidence.model_validate(record)

def test_exact_fact_estimate_and_misclassification():
 assert check()["status"]=="PASS"
 record=copy.deepcopy(RECORD)
 record["value"].update(calculation_type="estimated",formula="cost@1")
 assert check(record,manifest(record))["status"]=="PASS"
 assert check(RECORD,manifest(record))["status"]=="NEEDS_WORK"

@pytest.mark.parametrize("key,value",[("workspace_id",2),("source_id","record_2"),
 ("metric","revenue"),("source_version","snapshot@2"),("source_sha256","b"*64),
 ("captured_at","2026-10-18T11:58:00Z")])
def test_scope_and_provenance_not_just_number(key,value):
 claim=copy.deepcopy(RECORD)
 claim[key]=value
 assert check(claim)["status"]=="NEEDS_WORK"

@pytest.mark.parametrize("key,value",[("amount","999.00"),("unit","count"),
 ("source","user_input"),("period_from","2026-10-15"),("period_to","2026-10-18"),
 ("snapshot_id",2),("rule_version","cost@2")])
def test_value_mismatch(key,value):
 claim=copy.deepcopy(RECORD)
 claim["value"][key]=value
 assert check(claim)["status"]=="NEEDS_WORK"

@pytest.mark.parametrize("captured",["2026-10-17T12:00:00Z","2026-10-19T12:00:00Z"])
def test_stale_or_future_blocked(captured):
 record=copy.deepcopy(RECORD)
 record["captured_at"]=captured
 assert check(record,manifest(record))["status"]=="BLOCKED"

def test_missing_unavailable_partial():
 record=copy.deepcopy(RECORD)
 record["id"]="missing"
 assert check(record)["status"]=="BLOCKED"
 record=copy.deepcopy(RECORD)
 record["value"].update(amount=None,calculation_type="unavailable",data_sufficiency="insufficient",unavailable_reason="source_missing")
 assert check(record,manifest(record))["status"]=="BLOCKED"
 record=copy.deepcopy(RECORD)
 record["value"]["data_status"]="partial"
 assert check(record,manifest(record))["status"]=="NEEDS_WORK"

def test_invalid_manifest_and_extra_fields():
 raw=manifest()
 raw["workspace_id"]=2
 with pytest.raises(ValidationError):
     Manifest.model_validate(raw)
 raw=manifest()
 raw["evidence"]*=2
 with pytest.raises(ValidationError):
     Manifest.model_validate(raw)
 record=copy.deepcopy(RECORD)
 record["token"]="synthetic-not-a-secret"
 with pytest.raises(ValidationError):
     Evidence.model_validate(record)

def test_empty_and_synthetic_mismatch():
 submission=Submission(schema_version=1,synthetic=True,claims=[])
 assert verify(submission,Manifest.model_validate(manifest()),now=NOW)["status"]=="BLOCKED"
 submission=Submission(schema_version=1,synthetic=False,claims=[Evidence.model_validate(RECORD)])
 assert verify(submission,Manifest.model_validate(manifest()),now=NOW)["status"]=="NEEDS_WORK"

def test_duplicate_json_oversize_float(tmp_path):
 path=tmp_path/"input.json"
 path.write_text('{"schema_version":1,"schema_version":1}',encoding="utf-8")
 with pytest.raises(ValueError):
     load(path,Submission)
 path.write_bytes(b" "*(MAX_BYTES+1))
 with pytest.raises(ValueError):
     load(path,Submission)
 record=copy.deepcopy(RECORD)
 record["value"]["amount"]=0.1
 with pytest.raises(ValidationError):
     Evidence.model_validate(record)

def test_cli_no_sensitive_echo(tmp_path):
 path=tmp_path/"input.json"
 path.write_text('{"secret":"synthetic-sensitive-marker"}',encoding="utf-8")
 result=subprocess.run([sys.executable,"-m","app.agents","verify",str(path),"--evidence",str(path)],
 capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1],check=False)
 assert result.returncode==1
 assert json.loads(result.stdout)["status"]=="BLOCKED"
 assert "synthetic-sensitive-marker" not in result.stdout+result.stderr


def test_cli_valid_synthetic_and_no_arbitrary_text(tmp_path):
 record=copy.deepcopy(RECORD)
 record["captured_at"]=datetime.now(timezone.utc).isoformat()
 evidence=tmp_path/"trusted.json"
 claims=tmp_path/"claims.json"
 evidence.write_text(json.dumps(manifest(record)),encoding="utf-8")
 submission={"schema_version":1,"synthetic":True,"claims":[record]}
 claims.write_text(json.dumps(submission),encoding="utf-8")
 result=subprocess.run([sys.executable,"-m","app.agents","verify",str(claims),"--evidence",str(evidence)],
 capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1],check=False)
 assert result.returncode==0
 report=json.loads(result.stdout)
 assert report["status"]=="PASS" and report["synthetic"] is True
 assert report["authenticity_verified"] is False
 assert report["scope"]=="structured_claims_only"
 submission["summary"]="Invented revenue 999999"
 with pytest.raises(ValidationError):
     Submission.model_validate(submission)
