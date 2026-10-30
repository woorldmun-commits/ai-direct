CREATE TABLE worker_heartbeats (
  name text PRIMARY KEY CHECK (name ~ '^[a-z_]+$'),
  started_at timestamptz NOT NULL DEFAULT now(),
  heartbeat_at timestamptz NOT NULL,
  last_success_at timestamptz,
  phase text NOT NULL CHECK (phase IN ('idle','sync','measurement','verification','mail')),
  last_error_code text CHECK (last_error_code ~ '^[a-z_]+$')
);
REVOKE ALL ON worker_heartbeats FROM PUBLIC, app_rw, app_token, app_deleter;
GRANT SELECT, INSERT, UPDATE ON worker_heartbeats TO app_system;

CREATE TABLE workspace_email_preferences (
  workspace_id bigint NOT NULL REFERENCES workspaces ON DELETE CASCADE,
  user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
  enabled boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id,user_id)
);
ALTER TABLE workspace_email_preferences ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant ON workspace_email_preferences TO app_rw
  USING (workspace_id=app_workspace_id()) WITH CHECK (workspace_id=app_workspace_id());
CREATE POLICY system ON workspace_email_preferences TO app_system USING (true) WITH CHECK (true);
GRANT SELECT,INSERT,UPDATE ON workspace_email_preferences TO app_rw;

ALTER TABLE notifications ADD COLUMN recipient_user_id bigint REFERENCES users ON DELETE SET NULL;
ALTER TABLE notifications ADD COLUMN available_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE notifications ADD COLUMN locked_until timestamptz;
ALTER TABLE notifications ADD COLUMN lease_token uuid;
ALTER TABLE notifications ADD COLUMN last_error_code text CHECK (last_error_code ~ '^[a-z_]+$');

CREATE FUNCTION product_email_recipients(wid bigint)
RETURNS TABLE(user_id bigint,email text) LANGUAGE sql SECURITY DEFINER SET search_path=public,pg_temp AS $$
 SELECT p.user_id,c.email FROM workspace_email_preferences p
 JOIN effective_workspace_access a ON a.workspace_id=p.workspace_id AND a.user_id=p.user_id
 JOIN users u ON u.id=p.user_id AND u.status='active'
 JOIN email_credentials c ON c.user_id=p.user_id AND c.verified_at IS NOT NULL
 JOIN workspaces w ON w.id=p.workspace_id AND w.status='active'
 WHERE p.workspace_id=wid AND p.enabled
$$;
REVOKE ALL ON FUNCTION product_email_recipients(bigint) FROM PUBLIC,app_rw,app_token,app_deleter;
GRANT EXECUTE ON FUNCTION product_email_recipients(bigint) TO app_system;

CREATE FUNCTION product_email_available(actor bigint,wid bigint)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
 IF app_workspace_id() IS DISTINCT FROM wid OR workspace_role(actor,wid) IS NULL THEN
  RAISE EXCEPTION 'workspace unavailable' USING ERRCODE='insufficient_privilege';
 END IF;
 RETURN EXISTS(SELECT 1 FROM email_credentials c JOIN users u ON u.id=c.user_id
               WHERE c.user_id=actor AND c.verified_at IS NOT NULL AND u.status='active');
END $$;
REVOKE ALL ON FUNCTION product_email_available(bigint,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION product_email_available(bigint,bigint) TO app_rw;
