-- Independent read-only verification. No recommendation event types or advertising writes.
CREATE TABLE recommendation_verification_jobs (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 workspace_id bigint NOT NULL REFERENCES workspaces,
 recommendation_id bigint NOT NULL REFERENCES recommendations,
 finding_id bigint NOT NULL REFERENCES findings,
 done_event_id bigint NOT NULL UNIQUE REFERENCES recommendation_events,
 requested_by bigint NOT NULL REFERENCES users,
 idempotency_key uuid NOT NULL,
 request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 method text NOT NULL CHECK(method = 'excluded_sites_membership@1'),
 created_at timestamptz NOT NULL DEFAULT now(),
 available_at timestamptz NOT NULL DEFAULT now(),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 5),
 finished_at timestamptz,
 last_error text,
 UNIQUE(workspace_id,idempotency_key),
 UNIQUE(id,workspace_id)
);
CREATE INDEX recommendation_verification_due ON recommendation_verification_jobs(available_at,id) WHERE finished_at IS NULL;
CREATE FUNCTION check_verification_job() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' AND (NEW.id,NEW.workspace_id,NEW.recommendation_id,NEW.finding_id,NEW.done_event_id,
    NEW.requested_by,NEW.idempotency_key,NEW.request_sha256,NEW.method,NEW.created_at)
    IS DISTINCT FROM (OLD.id,OLD.workspace_id,OLD.recommendation_id,OLD.finding_id,OLD.done_event_id,
    OLD.requested_by,OLD.idempotency_key,OLD.request_sha256,OLD.method,OLD.created_at) THEN
    RAISE EXCEPTION 'verification identity is immutable' USING ERRCODE='integrity_constraint_violation';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM recommendation_events e JOIN issues i ON i.id=e.issue_id
    WHERE e.id=NEW.done_event_id AND e.type='done' AND e.recommendation_id=NEW.recommendation_id
    AND e.finding_id=NEW.finding_id AND i.workspace_id=NEW.workspace_id) THEN
    RAISE EXCEPTION 'verification must reference the exact manual done finding' USING ERRCODE='integrity_constraint_violation';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER recommendation_verification_identity BEFORE INSERT OR UPDATE ON recommendation_verification_jobs
 FOR EACH ROW EXECUTE FUNCTION check_verification_job();
CREATE TABLE recommendation_verification_reads (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 job_id bigint NOT NULL,
 workspace_id bigint NOT NULL REFERENCES workspaces,
 release_id bigint NOT NULL REFERENCES releases,
 attempt integer NOT NULL CHECK(attempt BETWEEN 1 AND 5),
 read_at timestamptz NOT NULL,
 status text NOT NULL CHECK(status IN ('confirmed','not_confirmed','unknown','unavailable')),
 reason text NOT NULL,
 params_hash text CHECK(params_hash ~ '^[0-9a-f]{64}$'),
 target_count integer NOT NULL CHECK(target_count>=0),
 matched_count integer NOT NULL CHECK(matched_count>=0 AND matched_count<=target_count),
 masked_count integer NOT NULL CHECK(masked_count>=0),
 FOREIGN KEY(job_id,workspace_id) REFERENCES recommendation_verification_jobs(id,workspace_id),
 UNIQUE(job_id,attempt),
 CHECK(status<>'confirmed' OR (target_count>0 AND matched_count=target_count AND params_hash IS NOT NULL)),
 CHECK(status<>'not_confirmed' OR (target_count>matched_count AND masked_count=0 AND params_hash IS NOT NULL)),
 CHECK(status<>'unknown' OR (target_count>matched_count AND masked_count>0 AND params_hash IS NOT NULL))
);
CREATE TRIGGER recommendation_verification_reads_append_only BEFORE UPDATE OR DELETE ON recommendation_verification_reads
 FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
ALTER TABLE recommendation_verification_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendation_verification_reads ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant ON recommendation_verification_jobs TO app_rw USING(workspace_id=app_workspace_id());
CREATE POLICY system ON recommendation_verification_jobs TO app_system USING(true) WITH CHECK(true);
CREATE POLICY tenant ON recommendation_verification_reads TO app_rw USING(workspace_id=app_workspace_id());
CREATE POLICY system ON recommendation_verification_reads TO app_system USING(true) WITH CHECK(true);
REVOKE ALL ON recommendation_verification_jobs,recommendation_verification_reads FROM PUBLIC;
GRANT SELECT,INSERT ON recommendation_verification_jobs TO app_rw;
GRANT SELECT ON recommendation_verification_reads TO app_rw;
REVOKE INSERT ON recommendation_verification_reads FROM app_rw;
GRANT INSERT ON recommendation_verification_reads TO app_token;
GRANT UPDATE(available_at,attempts,finished_at,last_error) ON recommendation_verification_jobs TO app_token,app_system;
GRANT USAGE ON SEQUENCE recommendation_verification_jobs_id_seq,recommendation_verification_reads_id_seq TO app_rw;
REVOKE ALL ON FUNCTION check_verification_job() FROM PUBLIC;
CREATE OR REPLACE FUNCTION delete_workspace_data(ws bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  counts jsonb := '{}';
  n bigint;
  org bigint;
  last_in_org boolean;
  sole_users bigint[] := '{}';
BEGIN
  PERFORM pg_advisory_xact_lock(ws);  -- ждёт записи снимков/аудитов, не пускает новые (DATA_MODEL.md §9.2)
  PERFORM set_config('app.deleting', 'on', true);
  IF (SELECT status FROM workspaces WHERE id = ws) IS DISTINCT FROM 'deletion_pending' THEN
    RAISE EXCEPTION 'workspace % is not in deletion_pending', ws;
  END IF;

  SELECT organization_id INTO org FROM workspaces WHERE id = ws;
  PERFORM 1 FROM organizations WHERE id = org FOR UPDATE;  -- параллельное удаление соседнего workspace ждёт
  last_in_org := NOT EXISTS (SELECT 1 FROM workspaces WHERE organization_id = org AND id <> ws);
  IF last_in_org THEN
    SELECT coalesce(array_agg(m.user_id), '{}') INTO sole_users
    FROM organization_memberships m
    WHERE m.organization_id = org
      AND NOT EXISTS (SELECT 1 FROM organization_memberships o
                      WHERE o.user_id = m.user_id AND o.organization_id <> org);
  END IF;

  DELETE FROM recommendation_verification_reads WHERE workspace_id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('recommendation_verification_reads', n);
  DELETE FROM recommendation_verification_jobs WHERE workspace_id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('recommendation_verification_jobs', n);
  DELETE FROM outbox_events WHERE workspace_id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('outbox_events', n);
  DELETE FROM notifications WHERE workspace_id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('notifications', n);
  DELETE FROM digests WHERE workspace_id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('digests', n);
  -- цикл ссылок: measured → результат → замер → done; удаляем в этом порядке
  DELETE FROM recommendation_events WHERE type = 'measured' AND recommendation_id IN
    (SELECT r.id FROM recommendations r JOIN issues i ON i.id = r.issue_id WHERE i.workspace_id = ws);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('recommendation_events_measured', n);
  DELETE FROM recommendation_results WHERE recommendation_id IN
    (SELECT r.id FROM recommendations r JOIN issues i ON i.id = r.issue_id WHERE i.workspace_id = ws);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('recommendation_results', n);
  DELETE FROM measurements WHERE recommendation_id IN
    (SELECT r.id FROM recommendations r JOIN issues i ON i.id = r.issue_id WHERE i.workspace_id = ws);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('measurements', n);
  DELETE FROM recommendation_events WHERE recommendation_id IN
    (SELECT r.id FROM recommendations r JOIN issues i ON i.id = r.issue_id WHERE i.workspace_id = ws);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('recommendation_events', n);
  DELETE FROM recommendations WHERE issue_id IN (SELECT id FROM issues WHERE workspace_id = ws);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('recommendations', n);
  DELETE FROM explanations WHERE finding_id IN
    (SELECT f.id FROM findings f JOIN issues i ON i.id = f.issue_id WHERE i.workspace_id = ws);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('explanations', n);
  DELETE FROM findings WHERE issue_id IN (SELECT id FROM issues WHERE workspace_id = ws);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('findings', n);
  DELETE FROM issues WHERE workspace_id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('issues', n);
  DELETE FROM audit_run_snapshots WHERE audit_run_id IN (SELECT id FROM audit_runs WHERE workspace_id = ws);
  DELETE FROM audit_runs WHERE workspace_id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('audit_runs', n);
  DELETE FROM stat_rows WHERE snapshot_id IN (SELECT id FROM snapshots WHERE workspace_id = ws);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('stat_rows', n);
  DELETE FROM snapshots WHERE workspace_id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('snapshots', n);
  DELETE FROM sync_runs WHERE workspace_id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('sync_runs', n);
  DELETE FROM search_query_sightings WHERE query_id IN (SELECT id FROM search_query_texts WHERE workspace_id = ws);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('search_query_sightings', n);
  DELETE FROM search_query_texts WHERE workspace_id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('search_query_texts', n);
  DELETE FROM placement_names WHERE workspace_id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('placement_names', n);
  UPDATE payments SET subscription_id = NULL
    WHERE subscription_id IN (SELECT id FROM subscriptions WHERE workspace_id = ws);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('payments_anonymized', n);
  DELETE FROM subscription_events WHERE subscription_id IN (SELECT id FROM subscriptions WHERE workspace_id = ws);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('subscription_events', n);
  DELETE FROM subscriptions WHERE workspace_id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('subscriptions', n);
  DELETE FROM metrika_counters WHERE metrika_connection_id IN (SELECT id FROM metrika_connections WHERE workspace_id = ws);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('metrika_counters', n);
  DELETE FROM metrika_connections WHERE workspace_id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('metrika_connections', n);
  DELETE FROM direct_accounts WHERE direct_connection_id IN (SELECT id FROM direct_connections WHERE workspace_id = ws);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('direct_accounts', n);
  DELETE FROM direct_connections WHERE workspace_id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('direct_connections', n);
  DELETE FROM workspace_settings WHERE workspace_id = ws;
  DELETE FROM workspace_memberships WHERE workspace_id = ws;
  DELETE FROM workspaces WHERE id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('workspaces', n);
  IF last_in_org THEN
    DELETE FROM organization_memberships WHERE organization_id = org;
    DELETE FROM organizations WHERE id = org;
    GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('organizations', n);
  END IF;

  DELETE FROM sessions WHERE user_id = ANY (sole_users);
  DELETE FROM telegram_links WHERE user_id = ANY (sole_users);
  DELETE FROM yandex_identities WHERE user_id = ANY (sole_users);
  -- принятия документов — доказательство: не удаляются, а обезличиваются (срок хранения — вопрос юристу, LEGAL.md)
  PERFORM set_config('app.anonymizing', 'on', true);
  UPDATE legal_acceptances SET user_id = NULL, ip = NULL, user_agent = NULL WHERE user_id = ANY (sole_users);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('legal_acceptances_anonymized', n);
  PERFORM set_config('app.anonymizing', 'off', true);
  DELETE FROM users WHERE id = ANY (sole_users);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('users', n);

  PERFORM set_config('app.deleting', 'off', true);
  RETURN counts;
END $$;
