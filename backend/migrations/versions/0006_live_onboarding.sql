-- Phone identity stores an HMAC and display suffix, never the raw number.
ALTER TABLE users ALTER COLUMN email DROP NOT NULL;
-- Metrika read scope does not disclose OAuth user identity. Bind one such connection to the workspace,
-- leaving unknown login NULL instead of requiring Direct access or inventing an identity.
ALTER TABLE metrika_connections ALTER COLUMN yandex_login DROP NOT NULL;
CREATE UNIQUE INDEX metrika_connections_without_login ON metrika_connections(workspace_id)
 WHERE yandex_login IS NULL;
CREATE TABLE phone_identities (
  user_id bigint PRIMARY KEY REFERENCES users ON DELETE CASCADE,
  phone_hash bytea NOT NULL UNIQUE CHECK (length(phone_hash) = 32),
  last_four text NOT NULL CHECK (last_four ~ '^[0-9]{4}$')
);
CREATE TABLE business_profiles (
  workspace_id bigint PRIMARY KEY REFERENCES workspaces ON DELETE CASCADE,
  profile jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(profile) = 'object'),
  updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE business_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant ON business_profiles TO app_rw
  USING (workspace_id = app_workspace_id()) WITH CHECK (workspace_id = app_workspace_id());
CREATE POLICY system ON business_profiles TO app_system USING (true) WITH CHECK (true);
CREATE TABLE integration_oauth_states (
  state_hash bytea PRIMARY KEY CHECK (length(state_hash) = 32),
  user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
  session_hash bytea NOT NULL REFERENCES sessions(token_hash) ON DELETE CASCADE,
  workspace_id bigint NOT NULL REFERENCES workspaces ON DELETE CASCADE,
  provider text NOT NULL CHECK (provider IN ('yandex_direct', 'yandex_metrika')),
  expires_at timestamptz NOT NULL
);
ALTER TABLE integration_oauth_states ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant ON integration_oauth_states TO app_rw USING (workspace_id = app_workspace_id());
CREATE POLICY system ON integration_oauth_states TO app_system USING (true) WITH CHECK (true);
REVOKE ALL ON phone_identities, business_profiles, integration_oauth_states FROM PUBLIC;
GRANT SELECT, INSERT ON phone_identities TO app_rw;
GRANT SELECT, INSERT, UPDATE ON business_profiles TO app_rw;
REVOKE ALL ON integration_oauth_states FROM app_rw;
CREATE FUNCTION remember_oauth_state(actor bigint, session bytea, ws bigint, provider text, hash bytea)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF workspace_role(actor, ws) NOT IN ('owner', 'admin') OR workspace_role(actor, ws) IS NULL
    OR NOT EXISTS (SELECT 1 FROM sessions WHERE token_hash = session AND user_id = actor
                   AND revoked_at IS NULL AND expires_at > now()) THEN
    RAISE EXCEPTION 'not authorized' USING ERRCODE = 'insufficient_privilege';
  END IF;
  DELETE FROM integration_oauth_states WHERE expires_at <= now();
  -- Bound pending challenges per session; starting again invalidates that session's prior challenge.
  DELETE FROM integration_oauth_states WHERE session_hash = session;
  INSERT INTO integration_oauth_states VALUES (hash, actor, session, ws, provider, now() + interval '10 minutes');
END $$;
-- SELECT FOR UPDATE requires an UPDATE privilege. Append-only trigger still rejects writes.
GRANT UPDATE (id) ON recommendations TO app_rw;
CREATE FUNCTION claim_oauth_state(actor bigint, session bytea, provider text, hash bytea)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE ws bigint;
BEGIN
  DELETE FROM integration_oauth_states s WHERE s.state_hash = hash AND s.user_id = actor
    AND s.session_hash = session AND s.provider = claim_oauth_state.provider AND s.expires_at > now()
    AND EXISTS (SELECT 1 FROM sessions WHERE token_hash = session AND user_id = actor
                AND revoked_at IS NULL AND expires_at > now()) RETURNING workspace_id INTO ws;
  RETURN ws;
END $$;
REVOKE EXECUTE ON FUNCTION remember_oauth_state(bigint, bytea, bigint, text, bytea),
  claim_oauth_state(bigint, bytea, text, bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION remember_oauth_state(bigint, bytea, bigint, text, bytea),
  claim_oauth_state(bigint, bytea, text, bytea) TO app_rw;
GRANT UPDATE (expires_at, revoked_at) ON sessions TO app_rw;
CREATE TABLE integration_catalogs (
  workspace_id bigint NOT NULL REFERENCES workspaces ON DELETE CASCADE,
  provider text NOT NULL CHECK (provider IN ('yandex_direct','yandex_metrika')),
  connection_id bigint NOT NULL,
  catalog jsonb NOT NULL CHECK(jsonb_typeof(catalog)='object'),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(workspace_id,provider,connection_id)
);
ALTER TABLE integration_catalogs ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant ON integration_catalogs TO app_rw USING(workspace_id=app_workspace_id())
  WITH CHECK(workspace_id=app_workspace_id());
CREATE POLICY system ON integration_catalogs TO app_system USING(true) WITH CHECK(true);
REVOKE ALL ON integration_catalogs FROM PUBLIC;
GRANT SELECT,INSERT,UPDATE ON integration_catalogs TO app_rw;
-- Add the human acceptance event without relaxing any other evidence checks.
DO $$ DECLARE c record; BEGIN
  FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='recommendation_events'::regclass AND contype='c'
    AND (pg_get_constraintdef(oid) LIKE '%measurement_skipped%'
      OR pg_get_constraintdef(oid) LIKE '%actor_user_id IS NOT NULL%'
      OR pg_get_constraintdef(oid) LIKE '%finding_id IS NOT NULL%') LOOP
    EXECUTE format('ALTER TABLE recommendation_events DROP CONSTRAINT %I',c.conname);
  END LOOP;
END $$;
ALTER TABLE recommendation_events ADD CONSTRAINT recommendation_events_type_live
 CHECK(type IN('accepted','postponed','rejected','done','checked','unpostponed','seen_again','resolved','measured','measurement_skipped'));
ALTER TABLE recommendation_events ADD CONSTRAINT recommendation_events_actor_live
 CHECK((type IN('accepted','postponed','rejected','done','checked'))=(actor_user_id IS NOT NULL));
ALTER TABLE recommendation_events ADD CONSTRAINT recommendation_events_finding_live
 CHECK((type IN('accepted','seen_again','done','checked','measured'))=(finding_id IS NOT NULL));
CREATE OR REPLACE FUNCTION check_done_finding_was_shown() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE level text;
BEGIN
 IF NEW.type NOT IN ('accepted','done','checked') OR NEW.finding_id IS NULL THEN RETURN NEW; END IF;
 IF NOT (EXISTS(SELECT 1 FROM recommendations WHERE id=NEW.recommendation_id AND finding_id=NEW.finding_id)
  OR EXISTS(SELECT 1 FROM recommendation_events WHERE recommendation_id=NEW.recommendation_id
             AND type='seen_again' AND finding_id=NEW.finding_id)) THEN
  RAISE EXCEPTION 'finding % was never shown for recommendation %', NEW.finding_id, NEW.recommendation_id
    USING ERRCODE='integrity_constraint_violation';
 END IF;
 SELECT action_level INTO level FROM findings WHERE id=NEW.finding_id;
 IF NEW.type IN ('done','checked') AND (NEW.type='done')=(level='inspect_only') THEN
  RAISE EXCEPTION '% is not allowed for finding % with action level %', NEW.type, NEW.finding_id, level
    USING ERRCODE='integrity_constraint_violation';
 END IF;
 RETURN NEW;
END $$;
