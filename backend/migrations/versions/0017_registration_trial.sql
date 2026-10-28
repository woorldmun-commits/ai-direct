CREATE TABLE registration_trials (
  user_id bigint PRIMARY KEY REFERENCES users ON DELETE CASCADE,
  workspace_id bigint UNIQUE REFERENCES workspaces ON DELETE SET NULL,
  started_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  CHECK (ends_at-started_at=interval '168 hours')
);
REVOKE ALL ON registration_trials FROM PUBLIC,app_rw,app_token,app_system,app_deleter;

CREATE FUNCTION start_registration_trial(usr bigint,ws bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
  IF workspace_role(usr,ws) IS DISTINCT FROM 'owner' THEN
    RAISE EXCEPTION 'trial requires the workspace owner' USING ERRCODE='insufficient_privilege';
  END IF;
  INSERT INTO registration_trials(user_id,workspace_id,started_at,ends_at)
  VALUES(usr,ws,now(),now()+interval '168 hours') ON CONFLICT(user_id) DO NOTHING;
END $$;
REVOKE ALL ON FUNCTION start_registration_trial(bigint,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION start_registration_trial(bigint,bigint) TO app_rw;

CREATE FUNCTION workspace_trial(ws bigint) RETURNS TABLE(started_at timestamptz,ends_at timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
  IF session_user NOT IN ('app_system','app_migrator') AND app_workspace_id() IS DISTINCT FROM ws THEN
    RAISE EXCEPTION 'trial requires workspace context' USING ERRCODE='insufficient_privilege';
  END IF;
  PERFORM require_workspace_context(ws);
  RETURN QUERY SELECT t.started_at,t.ends_at FROM registration_trials t WHERE t.workspace_id=ws;
END $$;
REVOKE ALL ON FUNCTION workspace_trial(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION workspace_trial(bigint) TO app_rw;
