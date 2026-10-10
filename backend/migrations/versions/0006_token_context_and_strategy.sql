-- 0006: функции токенов требуют контекст workspace у прикладной роли; стратегия кампании в снимке.
-- Те же правки, что в schema.sql.
-- Прежняя проверка пропускала пустой app.workspace_id у любой роли: app_rw вне workspace_scope мог записать или
-- сбросить токен чужого workspace по номеру. Без контекста теперь — только app_system и app_token.
CREATE OR REPLACE FUNCTION require_workspace_context(ws bigint) RETURNS void
LANGUAGE plpgsql STABLE AS $$
DECLARE
  caller name := CASE WHEN current_setting('role') = 'none' THEN session_user ELSE current_setting('role')::name END;
BEGIN
  IF app_workspace_id() IS NULL THEN
    IF NOT (pg_has_role(caller, 'app_system', 'MEMBER') OR pg_has_role(caller, 'app_token', 'MEMBER')) THEN
      RAISE EXCEPTION 'workspace context is required' USING ERRCODE = 'insufficient_privilege';
    END IF;
  ELSIF app_workspace_id() IS DISTINCT FROM ws THEN
    RAISE EXCEPTION 'workspace % is not the current workspace', ws USING ERRCODE = 'insufficient_privilege';
  END IF;
END $$;

-- Стратегия кампании — часть снимка (неизменяема вместе с ним, snapshot_lifecycle). Старые снимки — '{}': стратегия
-- неизвестна, как и было. ADD COLUMN с DEFAULT не переписывает строки и не вызывает триггеров UPDATE.
ALTER TABLE snapshots ADD COLUMN campaign_strategies jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(campaign_strategies) = 'object'
    AND NOT jsonb_path_exists(campaign_strategies, '$.keyvalue() ? (!(@.key like_regex "^[1-9][0-9]{0,18}$")
      || !(@.value == "manual_bidding" || @.value == "auto_clicks" || @.value == "auto_cpc" || @.value == "auto_cpa"
           || @.value == "pay_for_conversion" || @.value == "max_conversions" || @.value == "serving_off"
           || @.value == "unsupported" || @.value == "unknown"))'));
