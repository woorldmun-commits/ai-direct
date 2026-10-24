-- Additive import-only analysis; legacy snapshots, Value and recommendation events stay unchanged.
CREATE TABLE intelligence_profiles (
  workspace_id bigint NOT NULL REFERENCES workspaces ON DELETE CASCADE,
  revision integer NOT NULL CHECK (revision > 0),
  payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
  created_by bigint NOT NULL REFERENCES users,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id, revision)
);
CREATE TABLE intelligence_imports (
  id uuid PRIMARY KEY,
  workspace_id bigint NOT NULL REFERENCES workspaces ON DELETE CASCADE,
  fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
  data_mode text NOT NULL CHECK (data_mode IN ('synthetic','imported')),
  payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
  created_by bigint NOT NULL REFERENCES users,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, fingerprint),
  UNIQUE (workspace_id, id)
);
CREATE TABLE intelligence_runs (
  id uuid PRIMARY KEY,
  workspace_id bigint NOT NULL REFERENCES workspaces ON DELETE CASCADE,
  import_id uuid NOT NULL,
  before_import_id uuid,
  profile_revision integer NOT NULL,
  idempotency_key uuid NOT NULL,
  request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
  payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
  created_by bigint NOT NULL REFERENCES users,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, idempotency_key),
  UNIQUE (workspace_id, id),
  FOREIGN KEY (workspace_id, import_id) REFERENCES intelligence_imports(workspace_id,id),
  FOREIGN KEY (workspace_id, before_import_id) REFERENCES intelligence_imports(workspace_id,id),
  FOREIGN KEY (workspace_id, profile_revision) REFERENCES intelligence_profiles(workspace_id,revision)
);
CREATE TABLE intelligence_decisions (
  workspace_id bigint NOT NULL REFERENCES workspaces ON DELETE CASCADE,
  run_id uuid NOT NULL,
  recommendation_id text NOT NULL CHECK (length(recommendation_id) BETWEEN 1 AND 100),
  revision integer NOT NULL CHECK (revision = 1),
  state_version integer NOT NULL CHECK (state_version > 0),
  status text NOT NULL CHECK (status IN ('approved','postponed','rejected','cancelled')),
  reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
  actor_id bigint NOT NULL REFERENCES users,
  idempotency_key uuid NOT NULL,
  request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id, run_id, recommendation_id, state_version),
  UNIQUE (workspace_id, idempotency_key),
  FOREIGN KEY (workspace_id, run_id) REFERENCES intelligence_runs(workspace_id,id)
);
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['intelligence_profiles','intelligence_imports','intelligence_runs','intelligence_decisions'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY tenant ON %I TO app_rw USING (workspace_id = app_workspace_id())', t);
    EXECUTE format('CREATE POLICY system ON %I TO app_system USING (true) WITH CHECK (true)', t);
    EXECUTE format('GRANT SELECT, INSERT ON %I TO app_rw', t);
  END LOOP;
END $$;
