"""Publication gate: independently reload the sealed input and frozen audit context."""
from decimal import Decimal

from app.rules import RULES
from app.rules.domain import AuditSettings, Finding, run
from app.sync.store import load_view

VERSION = 'snapshot_recompute@1'


class VerificationBlocked(ValueError):
    pass


def validate(source, settings, finding):
    rule = next((rule for rule in RULES if rule.rule_version == finding.rule_version), None)
    if rule is None or finding not in tuple(output for output in run(rule, source, settings) if isinstance(output, Finding)):
        raise VerificationBlocked('finding_does_not_match_sealed_source')


def _inputs(conn, audit_id, workspace_id, account_id, snapshot_id):
    row = conn.execute('''SELECT a.settings FROM audit_runs a JOIN audit_run_snapshots s ON s.audit_run_id=a.id
        WHERE a.id=%s AND a.workspace_id=%s AND s.direct_account_id=%s AND s.snapshot_id=%s''',
        (audit_id, workspace_id, account_id, snapshot_id)).fetchone()
    if row is None:
        raise VerificationBlocked('audit_scope_mismatch')
    source = load_view(conn, snapshot_id)
    if source.snapshot_id != snapshot_id or source.workspace_id != workspace_id or source.direct_account_id != account_id:
        raise VerificationBlocked('snapshot_scope_mismatch')
    target = row[0].get('target_cpa')
    settings = AuditSettings(Decimal(target) if target is not None else None, row[0].get('business_profile'))
    return source, settings


class PublicationVerifier:
    """One independent replay per rule/scope within the current audit transaction."""
    def __init__(self, conn, audit_id):
        self.conn, self.audit_id = conn, audit_id
        self._sources, self._expected = {}, {}

    def verify(self, workspace_id, account_id, snapshot_id, finding):
        scope = (workspace_id, account_id, snapshot_id)
        if scope not in self._sources:
            self._sources[scope] = _inputs(self.conn, self.audit_id, *scope)
        key = (*scope, finding.rule_version)
        if key not in self._expected:
            rule = next((r for r in RULES if r.rule_version == finding.rule_version), None)
            if rule is None:
                raise VerificationBlocked('unknown_rule')
            source, settings = self._sources[scope]
            self._expected[key] = {out.issue_key: out for out in run(rule, source, settings) if isinstance(out, Finding)}
        if self._expected[key].get(finding.issue_key) != finding:
            raise VerificationBlocked('finding_does_not_match_sealed_source')
        return VERSION


def verify(conn, audit_id, workspace_id, account_id, snapshot_id, finding):
    return PublicationVerifier(conn, audit_id).verify(workspace_id, account_id, snapshot_id, finding)
