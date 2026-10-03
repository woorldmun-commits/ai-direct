-- 0005: отчёт площадок как возможность снимка (snapshots.sources: direct_placements) и справочник имён площадок —
-- данные workspace (workspace_id в ключе, RLS, удаление вместе с workspace). Те же правки, что в schema.sql.
-- Прежний справочник был глобальным: по нему можно было узнать о площадках другого клиента, и имена не удалялись
-- с данными. Перенос строк не нужен (продакшена нет): глобальные строки удаляются вместе с таблицей, имена
-- заново пишет следующая синхронизация каждого workspace. На непустой БД корректно: DROP снимает и триггер.
ALTER TABLE snapshots DROP CONSTRAINT snapshots_sources_check;
ALTER TABLE snapshots ADD CONSTRAINT snapshots_sources_check
  CHECK (sources <@ array['yandex_direct', 'yandex_metrika', 'direct_placements'] AND 'yandex_direct' = ANY (sources));

DROP TABLE placement_names;
CREATE TABLE placement_names (  -- [A]
  workspace_id bigint NOT NULL REFERENCES workspaces,
  id           bigint NOT NULL CHECK (id >= 0),
  name         text NOT NULL CHECK (
    length(name) <= 253
    AND name ~ '^[0-9a-zа-яё]([0-9a-zа-яё-]{0,61}[0-9a-zа-яё])?(\.[0-9a-zа-яё]([0-9a-zа-яё-]{0,61}[0-9a-zа-яё])?)*$'
    AND name ~ '[a-zа-яё]'
    AND name !~ '(^|\.)[0-9]+(\.|$)'
    AND name !~ '(^|\.)([^.]*[0-9]){7}'
    AND name !~ '(^|\.)[^.]*([a-z][^.]*[а-яё]|[а-яё][^.]*[a-z])'),
  PRIMARY KEY (workspace_id, id)
);
CREATE TRIGGER placement_names_append_only BEFORE UPDATE OR DELETE ON placement_names
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
REVOKE ALL ON placement_names FROM PUBLIC;
GRANT SELECT, INSERT ON placement_names TO app_rw;
ALTER TABLE placement_names ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant ON placement_names TO app_rw USING (workspace_id = app_workspace_id());
CREATE POLICY system ON placement_names TO app_system USING (true) WITH CHECK (true);

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
