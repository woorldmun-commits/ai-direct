-- Durable, workspace-scoped Chief read-only diagnostic jobs tied to a completed audit.
-- No external AI, notifications, provider writes or financial-effect approval.
CREATE TABLE chief_analysis_jobs (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 workspace_id bigint NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 audit_run_id bigint NOT NULL UNIQUE REFERENCES audit_runs(id) ON DELETE CASCADE,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','completed','blocked','failed','skipped')),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 4),
 available_at timestamptz NOT NULL DEFAULT now(),
 created_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz,
 error_code text CHECK(error_code IS NULL OR error_code ~ '^[a-z_]{3,60}$'),
 report jsonb CHECK(report IS NULL OR jsonb_typeof(report)='object'),
 CHECK ((status IN ('completed','blocked','failed','skipped')) = (finished_at IS NOT NULL)),
 CHECK (status NOT IN ('queued','running') OR report IS NULL),
 CHECK (status <> 'completed' OR report IS NOT NULL)
);
CREATE INDEX chief_analysis_due ON chief_analysis_jobs(available_at,id)
 WHERE status IN ('queued','running');
CREATE INDEX chief_analysis_workspace_history ON chief_analysis_jobs(workspace_id,created_at DESC,id DESC);

CREATE FUNCTION verify_chief_job_workspace() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' AND (NEW.workspace_id,NEW.audit_run_id,NEW.created_at)
     IS DISTINCT FROM (OLD.workspace_id,OLD.audit_run_id,OLD.created_at) THEN
    RAISE EXCEPTION 'chief job identity is immutable';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM audit_runs a WHERE a.id=NEW.audit_run_id
                AND a.workspace_id=NEW.workspace_id) THEN
    RAISE EXCEPTION 'chief job audit workspace mismatch';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER chief_job_scope BEFORE INSERT OR UPDATE ON chief_analysis_jobs
 FOR EACH ROW EXECUTE FUNCTION verify_chief_job_workspace();

ALTER TABLE chief_analysis_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY chief_read ON chief_analysis_jobs TO app_rw
 USING (workspace_id=app_workspace_id());
CREATE POLICY chief_system ON chief_analysis_jobs TO app_system
 USING (true) WITH CHECK (true);
REVOKE ALL ON chief_analysis_jobs FROM PUBLIC;
REVOKE INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON chief_analysis_jobs FROM app_rw,app_token;
GRANT SELECT ON chief_analysis_jobs TO app_rw;
GRANT SELECT,INSERT,UPDATE(status,attempts,available_at,finished_at,error_code,report)
 ON chief_analysis_jobs TO app_system;
GRANT USAGE ON SEQUENCE chief_analysis_jobs_id_seq TO app_system;
REVOKE ALL ON FUNCTION verify_chief_job_workspace() FROM PUBLIC;
