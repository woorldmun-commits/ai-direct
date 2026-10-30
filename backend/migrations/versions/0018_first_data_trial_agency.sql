-- Keep consumed trials unchanged; new registrations reserve their trial until data arrives.
ALTER TABLE registration_trials ALTER COLUMN started_at DROP NOT NULL;
ALTER TABLE registration_trials ALTER COLUMN ends_at DROP NOT NULL;
ALTER TABLE registration_trials ADD CHECK ((started_at IS NULL) = (ends_at IS NULL));
CREATE OR REPLACE FUNCTION start_registration_trial(usr bigint,ws bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
  IF workspace_role(usr,ws) IS DISTINCT FROM 'owner' THEN
    RAISE EXCEPTION 'trial requires the workspace owner' USING ERRCODE='insufficient_privilege';
  END IF;
  INSERT INTO registration_trials(user_id,workspace_id) VALUES(usr,ws) ON CONFLICT(user_id) DO NOTHING;
END $$;

-- Use one timestamp: the duration is an exact contract, including at the microsecond boundary.
CREATE FUNCTION activate_first_data_trial() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE started timestamptz := clock_timestamp();
BEGIN
  IF NEW.status='complete' AND OLD.status<>'complete' AND 'yandex_direct'=ANY(NEW.sources) THEN
    UPDATE registration_trials SET started_at=started,ends_at=started+interval '168 hours'
    WHERE workspace_id=NEW.workspace_id AND started_at IS NULL;
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION activate_first_data_trial() FROM PUBLIC;
CREATE TRIGGER first_data_trial AFTER UPDATE OF status ON snapshots FOR EACH ROW
  EXECUTE FUNCTION activate_first_data_trial();

-- Membership grants billing access only. It grants no membership in another client's organization.
CREATE TABLE agency_workspaces (
  workspace_id bigint PRIMARY KEY REFERENCES workspaces ON DELETE CASCADE,
  billing_workspace_id bigint NOT NULL REFERENCES workspaces ON DELETE CASCADE,
  request_id uuid UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON agency_workspaces FROM PUBLIC,app_rw,app_token,app_system,app_deleter;

CREATE FUNCTION billing_workspace(ws bigint) RETURNS bigint
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
  IF session_user NOT IN ('app_system','app_migrator') AND app_workspace_id() IS DISTINCT FROM ws THEN
    RAISE EXCEPTION 'billing requires workspace context' USING ERRCODE='insufficient_privilege';
  END IF;
  PERFORM require_workspace_context(ws);
  RETURN coalesce((SELECT billing_workspace_id FROM agency_workspaces WHERE workspace_id=ws),ws);
END $$;
REVOKE ALL ON FUNCTION billing_workspace(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION billing_workspace(bigint) TO app_rw;

CREATE FUNCTION effective_subscription(ws bigint,at_time timestamptz)
RETURNS TABLE(status text,current_period_end timestamptz,plan text,price numeric,
              current_period_start timestamptz,auto_renew boolean)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE root bigint := billing_workspace(ws);
BEGIN
  RETURN QUERY SELECT s.status,s.current_period_end,s.plan,s.price,s.current_period_start,s.auto_renew
    FROM subscriptions s JOIN workspaces w ON w.id=s.workspace_id
    WHERE s.workspace_id=root AND s.current_period_start<=at_time
      AND (root=ws OR (w.status='active' AND s.plan='business_plus'))
    ORDER BY (s.status IN ('active','past_due','canceled')) DESC,s.current_period_end DESC,s.id DESC LIMIT 1;
END $$;
REVOKE ALL ON FUNCTION effective_subscription(bigint,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION effective_subscription(bigint,timestamptz) TO app_rw;

CREATE FUNCTION billing_scope(ws bigint,exclude_login text DEFAULT '',take_lock boolean DEFAULT false)
RETURNS TABLE(billing_workspace_id bigint,workspaces_used bigint,accounts_used bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE root bigint := billing_workspace(ws);
BEGIN
  IF take_lock THEN PERFORM pg_advisory_xact_lock(root); END IF;
  RETURN QUERY SELECT root,
    (SELECT count(*) FROM workspaces w WHERE w.id=root OR w.id IN
      (SELECT a.workspace_id FROM agency_workspaces a WHERE a.billing_workspace_id=root)),
    (SELECT count(DISTINCT (c.workspace_id,coalesce(a.client_login,c.yandex_login)))
      FROM direct_accounts a JOIN direct_connections c ON c.id=a.direct_connection_id
      WHERE (c.workspace_id=root OR c.workspace_id IN
        (SELECT m.workspace_id FROM agency_workspaces m WHERE m.billing_workspace_id=root))
      AND c.status<>'disconnected' AND a.is_selected
      AND NOT(c.workspace_id=ws AND coalesce(a.client_login,c.yandex_login)=exclude_login));
END $$;
REVOKE ALL ON FUNCTION billing_scope(bigint,text,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION billing_scope(bigint,text,boolean) TO app_rw;

CREATE FUNCTION create_agency_client(actor bigint,ws bigint,client_name text,operation uuid) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE org bigint; client bigint; root bigint := billing_workspace(ws);
BEGIN
  IF root<>ws OR workspace_role(actor,ws) IS DISTINCT FROM 'owner' THEN
    RAISE EXCEPTION 'only billing workspace owner can create clients' USING ERRCODE='insufficient_privilege';
  END IF;
  IF length(trim(client_name)) NOT BETWEEN 1 AND 120 THEN RAISE EXCEPTION 'invalid client name'; END IF;
  PERFORM pg_advisory_xact_lock(root);
  SELECT workspace_id INTO client FROM agency_workspaces WHERE request_id=operation AND billing_workspace_id=root;
  IF client IS NOT NULL THEN RETURN client; END IF;
  IF NOT EXISTS(SELECT 1 FROM effective_subscription(root,now()) s JOIN workspaces w ON w.id=root
    WHERE w.status='active' AND s.plan='business_plus'
      AND ((s.status IN ('active','past_due') AND now()<s.current_period_end+interval '3 days')
        OR (s.status='canceled' AND now()<s.current_period_end))) THEN
    RAISE EXCEPTION 'active agency subscription required' USING ERRCODE='check_violation';
  END IF;
  INSERT INTO agency_workspaces(workspace_id,billing_workspace_id) VALUES(root,root) ON CONFLICT DO NOTHING;
  IF (SELECT count(*) FROM agency_workspaces WHERE billing_workspace_id=root)>=5 THEN
    RAISE EXCEPTION 'agency workspace limit reached' USING ERRCODE='check_violation';
  END IF;
  org := create_organization(actor,trim(client_name),'business');
  client := create_workspace(actor,org,trim(client_name));
  INSERT INTO agency_workspaces(workspace_id,billing_workspace_id,request_id) VALUES(client,root,operation);
  RETURN client;
END $$;
REVOKE ALL ON FUNCTION create_agency_client(bigint,bigint,text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION create_agency_client(bigint,bigint,text,uuid) TO app_rw;

CREATE FUNCTION agency_clients(actor bigint,ws bigint)
RETURNS TABLE(workspace_id bigint,name text,status text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
  PERFORM require_workspace_context(ws);
  IF billing_workspace(ws)<>ws OR workspace_role(actor,ws) IS DISTINCT FROM 'owner' THEN
    RAISE EXCEPTION 'only billing owner can list clients' USING ERRCODE='insufficient_privilege';
  END IF;
  RETURN QUERY SELECT w.id,w.name,w.status FROM workspaces w WHERE w.id=ws OR w.id IN
    (SELECT a.workspace_id FROM agency_workspaces a WHERE a.billing_workspace_id=ws) ORDER BY w.id;
END $$;
REVOKE ALL ON FUNCTION agency_clients(bigint,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION agency_clients(bigint,bigint) TO app_rw;
