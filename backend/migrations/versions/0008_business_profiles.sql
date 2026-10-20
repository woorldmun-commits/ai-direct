-- 0008: профиль бизнеса workspace (онбординг): отрасль, модель, сайт (только хранится, не загружается), цели,
-- бюджет и целевой CPA. Данные workspace: RLS, удаляется вместе с workspace (ON DELETE CASCADE).
CREATE TABLE business_profiles (  -- [O]
  workspace_id bigint PRIMARY KEY REFERENCES workspaces ON DELETE CASCADE,
  profile      jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(profile) = 'object'),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON business_profiles FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON business_profiles TO app_rw;
ALTER TABLE business_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant ON business_profiles TO app_rw
  USING (workspace_id = app_workspace_id()) WITH CHECK (workspace_id = app_workspace_id());
CREATE POLICY system ON business_profiles TO app_system USING (true) WITH CHECK (true);
