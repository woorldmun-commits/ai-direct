"""Validate structured claims against independently trusted evidence using Value.

This checks consistency, not the authenticity of an arbitrary JSON evidence file.
The integration owner, not the submitting agent, must supply the manifest.
"""
from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from app.contract import Value

Identifier = Annotated[str, Field(pattern=r"\A[a-zA-Z0-9_.:@-]{1,100}\z", max_length=100)]
PositiveInt = Annotated[StrictInt, Field(gt=0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Evidence(StrictModel):
    id: Identifier
    workspace_id: PositiveInt
    metric: Identifier
    source_id: Identifier
    source_version: Identifier
    source_sha256: Annotated[str, Field(pattern=r"\A[a-f0-9]{64}\z", min_length=64, max_length=64)]
    captured_at: datetime
    value: Value

    @model_validator(mode="after")
    def aware_time(self):
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must include a timezone")
        return self


class Manifest(StrictModel):
    schema_version: Literal[1]
    synthetic: bool
    workspace_id: PositiveInt
    period_from: date
    period_to: date
    max_age_seconds: Annotated[StrictInt, Field(ge=1, le=2678400)]
    evidence: Annotated[list[Evidence], Field(max_length=1000)]

    @model_validator(mode="after")
    def scope(self):
        if self.period_from > self.period_to:
            raise ValueError("invalid period")
        if len({item.id for item in self.evidence}) != len(self.evidence):
            raise ValueError("duplicate evidence IDs")
        for item in self.evidence:
            if (item.workspace_id != self.workspace_id or
                    item.value.period_from != self.period_from or
                    item.value.period_to != self.period_to):
                raise ValueError("evidence outside trusted scope")
        return self


class Submission(StrictModel):
    schema_version: Literal[1]
    synthetic: bool
    claims: Annotated[list[Evidence], Field(max_length=1000)]

    @model_validator(mode="after")
    def unique(self):
        if len({item.id for item in self.claims}) != len(self.claims):
            raise ValueError("duplicate claim IDs")
        return self


def verify(submission: Submission, manifest: Manifest, *, now: datetime | None = None) -> dict:
    """Only trusted scope, provenance and exact Values can pass. No formula execution."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    issues = []
    rejected = False
    blocked = False
    if submission.synthetic != manifest.synthetic:
        issues.append({"index": None, "code": "synthetic_mismatch"})
        rejected = True
    records = {item.id: item for item in manifest.evidence}
    if not submission.claims:
        issues.append({"index": None, "code": "no_claims"})
        blocked = True
    for index, claim in enumerate(submission.claims):
        record = records.get(claim.id)
        if record is None:
            issues.append({"index": index, "code": "evidence_missing"})
            blocked = True
            continue
        # Equality includes workspace, source record/version/hash, metric, period,
        # unit, snapshot, formula, estimate classification and completeness.
        if claim != record:
            issues.append({"index": index, "code": "claim_evidence_mismatch"})
            rejected = True
            continue
        age = (now - record.captured_at).total_seconds()
        if age < 0 or age > manifest.max_age_seconds:
            issues.append({"index": index, "code": "evidence_not_current"})
            blocked = True
        if record.value.calculation_type == "unavailable":
            issues.append({"index": index, "code": "data_unavailable"})
            blocked = True
        elif record.value.data_status == "partial":
            issues.append({"index": index, "code": "data_partial"})
            rejected = True
    status = "NEEDS_WORK" if rejected else "BLOCKED" if blocked else "PASS"
    return {"schema_version": 1, "status": status, "synthetic": manifest.synthetic,
            "checked_claims": len(submission.claims), "issues": issues,
            "scope": "structured_claims_only", "authenticity_verified": False}
