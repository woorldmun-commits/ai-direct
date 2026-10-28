-- NULL + configured means an explicit choice to use Direct without a Metrika counter.
-- Existing accounts must reconnect; historical scheduled rows cannot prove the intended binding.
ALTER TABLE direct_accounts ADD COLUMN metrika_counter_id bigint REFERENCES metrika_counters
  DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE direct_accounts ADD COLUMN metrika_configured boolean NOT NULL DEFAULT false;
ALTER TABLE direct_accounts ADD CONSTRAINT direct_accounts_metrika_binding_check
  CHECK (metrika_configured OR metrika_counter_id IS NULL);

CREATE OR REPLACE FUNCTION check_same_workspace() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE ok boolean := true;
BEGIN
  IF TG_TABLE_NAME = 'sync_runs' THEN
    ok := EXISTS (SELECT 1 FROM direct_accounts a JOIN direct_connections c ON c.id = a.direct_connection_id
                  WHERE a.id = NEW.direct_account_id AND c.workspace_id = NEW.workspace_id)
      AND (NEW.metrika_counter_id IS NULL OR EXISTS (
            SELECT 1 FROM metrika_counters mc JOIN metrika_connections m ON m.id = mc.metrika_connection_id
            WHERE mc.id = NEW.metrika_counter_id AND m.workspace_id = NEW.workspace_id));
  ELSIF TG_TABLE_NAME = 'direct_accounts' THEN
    ok := NEW.metrika_counter_id IS NULL OR EXISTS (
      SELECT 1 FROM direct_connections d JOIN metrika_counters mc ON mc.id=NEW.metrika_counter_id
      JOIN metrika_connections m ON m.id=mc.metrika_connection_id
      WHERE d.id=NEW.direct_connection_id AND d.workspace_id=m.workspace_id);
  ELSIF TG_TABLE_NAME = 'issues' THEN
    ok := EXISTS (SELECT 1 FROM direct_accounts a JOIN direct_connections c ON c.id = a.direct_connection_id
                  WHERE a.id = NEW.direct_account_id AND c.workspace_id = NEW.workspace_id);
  ELSIF TG_TABLE_NAME IN ('digests', 'notifications') THEN
    ok := NEW.snapshot_id IS NULL
          OR EXISTS (SELECT 1 FROM snapshots s WHERE s.id = NEW.snapshot_id AND s.workspace_id = NEW.workspace_id);
  ELSIF TG_TABLE_NAME = 'recommendation_results' THEN
    ok := NEW.snapshot_id IS NULL OR EXISTS (SELECT 1 FROM snapshots s JOIN issues i ON i.id = NEW.issue_id
                  WHERE s.id = NEW.snapshot_id AND s.workspace_id = i.workspace_id);
  END IF;
  IF NOT ok THEN
    RAISE EXCEPTION '%: reference to another workspace', TG_TABLE_NAME USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END
$$;
CREATE TRIGGER direct_accounts_same_workspace BEFORE INSERT OR UPDATE ON direct_accounts
  FOR EACH ROW EXECUTE FUNCTION check_same_workspace();
