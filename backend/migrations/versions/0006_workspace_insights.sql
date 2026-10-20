-- Operational input only: no ad-platform writes, credentials or free-form contact data.
CREATE TABLE workspace_budget_plans (
  workspace_id bigint PRIMARY KEY REFERENCES workspaces ON DELETE CASCADE,
  period_from date NOT NULL,
  period_to date NOT NULL,
  amount numeric(14,2) NOT NULL CHECK (amount > 0),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (period_to >= period_from AND period_to - period_from < 366)
);
CREATE TABLE workspace_lead_imports (
  workspace_id bigint PRIMARY KEY REFERENCES workspaces ON DELETE CASCADE,
  fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
  period_from date,
  period_to date,
  cohort_complete boolean NOT NULL DEFAULT false,
  imported_ids uuid[] NOT NULL,
  imported_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((period_from IS NULL) = (period_to IS NULL)),
  CHECK (NOT cohort_complete OR period_from IS NOT NULL),
  CHECK (period_to >= period_from AND period_to - period_from < 366)
);
CREATE TABLE workspace_leads (
  workspace_id bigint NOT NULL REFERENCES workspaces ON DELETE CASCADE,
  external_id uuid NOT NULL,
  created_on date NOT NULL,
  acquired_on date,
  updated_on date NOT NULL,
  direct_account_id bigint NOT NULL,
  campaign_id bigint,
  status text NOT NULL CHECK (status IN ('new','qualified','rejected','won','lost','refunded')),
  amount numeric(14,2) CHECK (amount >= 0),
  refund_amount numeric(14,2) NOT NULL DEFAULT 0 CHECK (refund_amount >= 0),
  PRIMARY KEY (workspace_id, external_id),
  CHECK (updated_on >= created_on AND (acquired_on IS NULL OR acquired_on <= created_on)),
  CHECK (refund_amount = 0 OR (amount IS NOT NULL AND refund_amount <= amount)),
  CHECK (campaign_id IS NULL OR campaign_id > 0)
);
CREATE INDEX workspace_leads_cohort ON workspace_leads (workspace_id, created_on);
-- ON DELETE CASCADE integrates all three tables with delete_workspace_data without changing its security boundary.
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['workspace_budget_plans','workspace_lead_imports','workspace_leads'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY tenant ON %I TO app_rw USING (workspace_id = app_workspace_id())', t);
    EXECUTE format('CREATE POLICY system ON %I TO app_system USING (true) WITH CHECK (true)', t);
    EXECUTE format('GRANT SELECT, INSERT ON %I TO app_rw', t);
  END LOOP;
END $$;
GRANT UPDATE (period_from,period_to,amount,updated_at) ON workspace_budget_plans TO app_rw;
GRANT UPDATE (fingerprint,period_from,period_to,cohort_complete,imported_ids,imported_at)
  ON workspace_lead_imports TO app_rw;
GRANT UPDATE (updated_on,status,amount,refund_amount) ON workspace_leads TO app_rw;
CREATE FUNCTION workspace_lead_account_fit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM direct_accounts a JOIN direct_connections c ON c.id=a.direct_connection_id
                 WHERE a.id=NEW.direct_account_id AND c.workspace_id=NEW.workspace_id) THEN
    RAISE EXCEPTION 'lead account outside workspace' USING ERRCODE='integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER workspace_lead_account_fit BEFORE INSERT OR UPDATE ON workspace_leads
  FOR EACH ROW EXECUTE FUNCTION workspace_lead_account_fit();
