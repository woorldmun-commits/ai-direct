-- Схема MVP. Источник правды для первой миграции alembic.
-- Описание сущностей и состояний: docs/DATA_MODEL.md.
-- Выполняется ролью app_migrator (владелец всех объектов).
-- Роли app_rw, app_token (член app_rw), app_deleter, app_migrator создаются на уровне кластера
-- (Managed PostgreSQL / тестовый стенд): см. tests/conftest.py.

-- ============================================================================
-- Контракт данных
-- ============================================================================

-- Value: {"amount","unit","source","period_from","period_to","calculation_type",
--         "data_status","data_sufficiency","snapshot_id", ["rule_version"], ["formula"]}
-- Те же правила, что в backend/app/contract.py; согласованность проверяет tests/test_value_contract.py.
-- Ошибка приведения типа (например, 2026-02-30) трактуется как «невалидно», а не как исключение.
CREATE FUNCTION value_is_valid_raw(v jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT coalesce(
    jsonb_typeof(v) = 'object'
    AND v ?& array['amount', 'unit', 'source', 'period_from', 'period_to',
                   'calculation_type', 'data_status', 'data_sufficiency', 'snapshot_id']
    -- лишних ключей нет
    AND NOT EXISTS (SELECT 1 FROM jsonb_object_keys(v) AS k
                    WHERE k NOT IN ('amount', 'unit', 'source', 'period_from', 'period_to', 'calculation_type',
                                    'data_status', 'data_sufficiency', 'snapshot_id', 'rule_version', 'formula'))
    AND v->>'unit' IN ('rub', 'count', 'pct')
    AND jsonb_typeof(v->'source') = 'string'
    AND v->>'source' ~ '^(yandex_direct|yandex_metrika|user_input)(\+(yandex_direct|yandex_metrika|user_input))*$'
    AND v->>'calculation_type' IN ('actual', 'estimated', 'unavailable')
    AND v->>'data_status' IN ('complete', 'partial')
    AND v->>'data_sufficiency' IN ('sufficient', 'insufficient')
    -- insufficient ⇔ unavailable ⇔ amount = null
    AND (v->>'data_sufficiency' = 'insufficient') = (v->>'calculation_type' = 'unavailable')
    AND (v->>'calculation_type' = 'unavailable') = (jsonb_typeof(v->'amount') = 'null')
    AND (jsonb_typeof(v->'amount') = 'null'
         OR (jsonb_typeof(v->'amount') IN ('string', 'number') AND v->>'amount' ~ '^-?[0-9]+(\.[0-9]+)?$'))
    -- estimated ⇒ формула обязательна
    AND jsonb_typeof(coalesce(v->'formula', 'null'::jsonb)) IN ('null', 'string')
    AND (v->>'calculation_type' <> 'estimated' OR length(coalesce(v->>'formula', '')) > 0)
    AND jsonb_typeof(coalesce(v->'rule_version', 'null'::jsonb)) IN ('null', 'string')
    AND coalesce(v->>'rule_version' ~ '^[a-z0-9_]+@[0-9]+$', true)
    AND jsonb_typeof(v->'snapshot_id') = 'number' AND v->>'snapshot_id' ~ '^[0-9]+$'
    AND jsonb_typeof(v->'period_from') = 'string' AND jsonb_typeof(v->'period_to') = 'string'
    AND v->>'period_from' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' AND v->>'period_to' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    AND (v->>'period_from')::date <= (v->>'period_to')::date,
    false)
$$;

CREATE FUNCTION value_is_valid(v jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
  RETURN value_is_valid_raw(v);
EXCEPTION WHEN others THEN
  RETURN false;
END
$$;

-- evidence: {"имя": Value, ...}
CREATE FUNCTION evidence_is_valid(e jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT jsonb_typeof(e) = 'object'
     AND NOT EXISTS (SELECT 1 FROM jsonb_each(e) AS x WHERE NOT value_is_valid(x.value))
$$;

CREATE FUNCTION values_are_valid(a jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT jsonb_typeof(a) = 'array'
     AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(a) AS x WHERE NOT value_is_valid(x))
$$;

-- Append-only: UPDATE запрещён всем, DELETE — всем, кроме роли удаления.
-- Внешние ключи без CASCADE: каскад выполняется от имени владельца таблицы и упёрся бы в этот триггер.
-- DELETE пропускается только внутри функций удаления (delete_workspace_data, purge_search_query_texts): они
-- SECURITY DEFINER и ставят метку транзакции app.deleting. Обойти метку нельзя: ни у одной рабочей роли нет
-- права DELETE на эти таблицы — удалять можно только вызовом функции.
CREATE FUNCTION forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' AND current_setting('app.deleting', true) = 'on' THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'table % is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'insufficient_privilege';
END $$;

-- ============================================================================
-- Пользователи и доступ  [O]
-- ============================================================================

CREATE TABLE users (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email          text NOT NULL,
  status         text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deactivated')),
  created_at     timestamptz NOT NULL DEFAULT now(),
  deactivated_at timestamptz,
  CHECK ((status = 'deactivated') = (deactivated_at IS NOT NULL))
);

CREATE TABLE yandex_identities (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id    bigint NOT NULL UNIQUE REFERENCES users,
  yandex_uid text NOT NULL UNIQUE,
  login      text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- В cookie — случайный токен; в БД — только его sha256.
CREATE TABLE sessions (
  token_hash bytea PRIMARY KEY CHECK (length(token_hash) = 32),
  user_id    bigint NOT NULL REFERENCES users,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  CHECK (expires_at > created_at)
);

CREATE TABLE workspaces (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name           text NOT NULL,
  status         text NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active', 'deactivated', 'deletion_pending')),
  created_at     timestamptz NOT NULL DEFAULT now(),
  deactivated_at timestamptz,
  CHECK ((status = 'active') = (deactivated_at IS NULL))
);

CREATE TABLE memberships (
  user_id      bigint NOT NULL REFERENCES users,
  workspace_id bigint NOT NULL REFERENCES workspaces,
  role         text NOT NULL DEFAULT 'owner' CHECK (role IN ('owner')),
  PRIMARY KEY (user_id, workspace_id)
);

CREATE TABLE workspace_settings (
  workspace_id         bigint PRIMARY KEY REFERENCES workspaces,
  target_cpa           numeric(14, 2) CHECK (target_cpa > 0),
  avg_check            numeric(14, 2) CHECK (avg_check > 0),
  lead_to_sale_rate    numeric(5, 4) CHECK (lead_to_sale_rate > 0 AND lead_to_sale_rate <= 1),
  notify_pct_threshold smallint NOT NULL DEFAULT 10 CHECK (notify_pct_threshold IN (10, 15, 20)),
  attribution_model    text CHECK (attribution_model IN ('cross_device_last_significant', 'last', 'cross_device_first', 'automatic')),
  updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE telegram_links (
  user_id   bigint PRIMARY KEY REFERENCES users,
  chat_id   bigint NOT NULL UNIQUE,
  linked_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- Подключения  [O]
-- ============================================================================

CREATE TABLE direct_connections (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id      bigint NOT NULL REFERENCES workspaces,
  yandex_login      text NOT NULL,
  token_enc         bytea,
  token_expires_at  timestamptz,
  scopes            text[] NOT NULL DEFAULT '{}',
  status            text NOT NULL CHECK (status IN ('connected', 'permission_missing', 'token_expired',
                                                    'token_revoked', 'api_error', 'disconnected')),
  status_detail     text,
  status_changed_at timestamptz NOT NULL DEFAULT now(),
  last_sync_at      timestamptz,
  has_token         boolean NOT NULL GENERATED ALWAYS AS (token_enc IS NOT NULL) STORED,  -- без доступа к шифротексту
  last_success_at   timestamptz,  -- последний успешный авторизованный запрос к API
  last_error        text,         -- последняя ошибка API (код), история попыток — в sync_runs
  last_error_at     timestamptz,
  CHECK ((last_error IS NULL) = (last_error_at IS NULL)),
  UNIQUE (workspace_id, yandex_login),
  -- отключено / отозвано ⇒ токена в БД нет
  CHECK (status NOT IN ('disconnected', 'token_revoked') OR token_enc IS NULL),
  CHECK (status <> 'connected' OR token_enc IS NOT NULL)
);

CREATE TABLE direct_accounts (
  id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  direct_connection_id bigint NOT NULL REFERENCES direct_connections,
  client_login         text,  -- NULL: собственный аккаунт; иначе доступ через Client-Login
  is_selected          boolean NOT NULL DEFAULT false,
  status               text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'unavailable')),
  -- по фактическому ответу API: access_denied · account_not_found · api_restricted
  unavailable_reason   text CHECK (unavailable_reason IN ('access_denied', 'account_not_found', 'api_restricted')),
  CHECK ((status = 'unavailable') = (unavailable_reason IS NOT NULL))
);
CREATE UNIQUE INDEX direct_accounts_login_uq
  ON direct_accounts (direct_connection_id, coalesce(client_login, ''));
-- ponytail: в MVP один выбранный аккаунт на подключение; снять индекс для Бизнес+
CREATE UNIQUE INDEX direct_accounts_one_selected
  ON direct_accounts (direct_connection_id) WHERE is_selected;

CREATE TABLE metrika_connections (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id      bigint NOT NULL REFERENCES workspaces,
  yandex_login      text NOT NULL,
  token_enc         bytea,
  token_expires_at  timestamptz,
  scopes            text[] NOT NULL DEFAULT '{}',
  status            text NOT NULL CHECK (status IN ('connected', 'permission_missing', 'token_expired',
                                                    'token_revoked', 'api_error', 'disconnected')),
  status_detail     text,
  status_changed_at timestamptz NOT NULL DEFAULT now(),
  last_sync_at      timestamptz,
  has_token         boolean NOT NULL GENERATED ALWAYS AS (token_enc IS NOT NULL) STORED,  -- без доступа к шифротексту
  last_success_at   timestamptz,  -- последний успешный авторизованный запрос к API
  last_error        text,         -- последняя ошибка API (код), история попыток — в sync_runs
  last_error_at     timestamptz,
  CHECK ((last_error IS NULL) = (last_error_at IS NULL)),
  UNIQUE (workspace_id, yandex_login),
  CHECK (status NOT IN ('disconnected', 'token_revoked') OR token_enc IS NULL),
  CHECK (status <> 'connected' OR token_enc IS NOT NULL)
);

CREATE TABLE metrika_counters (
  id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  metrika_connection_id bigint NOT NULL REFERENCES metrika_connections,
  counter_id            bigint NOT NULL,
  is_selected           boolean NOT NULL DEFAULT false,
  goal_ids              bigint[] NOT NULL DEFAULT '{}' CHECK (cardinality(goal_ids) <= 10),  -- предел Goals Директа
  UNIQUE (metrika_connection_id, counter_id),
  CHECK (NOT is_selected OR cardinality(goal_ids) > 0)
);
CREATE UNIQUE INDEX metrika_counters_one_selected
  ON metrika_counters (metrika_connection_id) WHERE is_selected;

-- ============================================================================
-- Доказательная цепочка  [A] — кроме sync_runs и issues
-- ============================================================================

CREATE TABLE releases (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  commit_sha  text NOT NULL CHECK (commit_sha ~ '^[0-9a-f]{40}$'),
  build_id    text NOT NULL,
  released_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (commit_sha, build_id)
);

CREATE TABLE sync_runs (  -- [O]
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id       bigint NOT NULL REFERENCES workspaces,
  direct_account_id  bigint NOT NULL REFERENCES direct_accounts,
  metrika_counter_id bigint REFERENCES metrika_counters,
  kind               text NOT NULL CHECK (kind IN ('free_audit', 'scheduled', 'resync')),
  status             text NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued', 'running', 'waiting_report', 'succeeded', 'failed', 'skipped')),
  started_at         timestamptz,  -- первый запрос отчёта: от него считается предельное ожидание
  finished_at        timestamptz,
  attempts           smallint NOT NULL DEFAULT 0 CHECK (attempts >= 0),  -- сколько раз отчёт был «не готов»
  last_retry_at      timestamptz,
  error_code         text,  -- failed: access_denied · invalid_report_format · … ; skipped: причина guard
  error_reason       text CHECK (error_reason ~ '^[a-z_]+$'),  -- код причины: negative_value, … (не текст сервера)
  CHECK ((status IN ('succeeded', 'failed', 'skipped')) = (finished_at IS NOT NULL)),
  CHECK (status NOT IN ('failed', 'skipped') OR error_code IS NOT NULL),
  CHECK (error_reason IS NULL OR error_code IS NOT NULL)
);

CREATE TABLE snapshots (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id bigint NOT NULL REFERENCES workspaces,
  sync_run_id  bigint NOT NULL UNIQUE REFERENCES sync_runs,
  release_id   bigint NOT NULL REFERENCES releases,
  created_at   timestamptz NOT NULL DEFAULT now(),
  period_from  date NOT NULL,
  period_to    date NOT NULL,
  data_until   timestamptz NOT NULL,
  partial_from date NOT NULL,  -- даты >= partial_from → data_status = partial
  sources      text[] NOT NULL CHECK (sources <@ array['yandex_direct', 'yandex_metrika']
                                      AND 'yandex_direct' = ANY (sources)),
  -- Что считалось конверсией: счётчик, цели, атрибуция — копия на момент синхронизации (sources/conversion.py).
  -- Конверсии кампаний в stat_rows(yandex_direct) — данные Метрики из отчёта Директа по этому определению.
  -- NULL: цели не выбраны, конверсий в снимке нет.
  conversion_definition jsonb CHECK (conversion_definition IS NULL OR (
    jsonb_typeof(conversion_definition) = 'object'
    AND conversion_definition->>'provider' = 'yandex_metrika'
    AND jsonb_typeof(conversion_definition->'counter_id') = 'number'
    AND jsonb_typeof(conversion_definition->'goal_ids') = 'array'
    AND jsonb_array_length(conversion_definition->'goal_ids') BETWEEN 1 AND 10
    AND conversion_definition->>'attribution' IN ('cross_device_last_significant', 'last', 'cross_device_first', 'automatic'))),
  -- Необязательный источник, который не удалось получить: {"yandex_metrika": "access_denied"}.
  -- Директ здесь не бывает: без отчёта Директа снимка нет вовсе (sync_run.failed).
  source_failures jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(source_failures) = 'object'
                                                     AND source_failures - 'yandex_metrika' = '{}'::jsonb),
  CHECK (NOT ('yandex_metrika' = ANY (sources) AND source_failures ? 'yandex_metrika')),
  CHECK (NOT 'yandex_metrika' = ANY (sources) OR conversion_definition IS NOT NULL),
  status       text NOT NULL DEFAULT 'building' CHECK (status IN ('building', 'complete', 'failed')),
  sealed_at    timestamptz,
  CHECK ((status = 'complete') = (sealed_at IS NOT NULL)),
  CHECK (period_from <= period_to),
  CHECK (partial_from BETWEEN period_from AND period_to + 1)
);

CREATE TABLE stat_rows (
  snapshot_id bigint NOT NULL REFERENCES snapshots,
  source      text NOT NULL CHECK (source IN ('yandex_direct', 'yandex_metrika')),
  level       text NOT NULL CHECK (level IN ('campaign', 'adgroup', 'query', 'placement',
                                             'hour', 'region', 'site_goal')),
  object_id   bigint NOT NULL,  -- для level = query: search_query_texts.id (без FK: текст удаляется раньше агрегатов)
  campaign_id bigint,
  date        date NOT NULL,
  impressions bigint NOT NULL DEFAULT 0 CHECK (impressions >= 0),
  clicks      bigint NOT NULL DEFAULT 0 CHECK (clicks >= 0),
  cost        numeric(14, 2) NOT NULL DEFAULT 0 CHECK (cost >= 0),
  conversions numeric(12, 2) CHECK (conversions >= 0),  -- NULL: Метрика не подключена
  revenue     numeric(14, 2) CHECK (revenue >= 0),
  -- уровни Директа всегда внутри кампании; без кампании — только цели сайта из Метрики
  CHECK ((level = 'site_goal') = (campaign_id IS NULL)),
  -- на уровне кампании объект и есть кампания: ключ не расширяется искусственно
  CHECK (level <> 'campaign' OR object_id = campaign_id)
);
-- Одна строка = одно статистическое наблюдение. Зернистость: снимок · источник · уровень · кампания · объект · день.
-- Один и тот же запрос в двух кампаниях за день — две строки.
CREATE UNIQUE INDEX stat_rows_grain ON stat_rows (snapshot_id, source, level, campaign_id, object_id, date)
  WHERE campaign_id IS NOT NULL;
CREATE UNIQUE INDEX stat_rows_grain_no_campaign ON stat_rows (snapshot_id, source, level, object_id, date)
  WHERE campaign_id IS NULL;
CREATE INDEX stat_rows_audit ON stat_rows (snapshot_id, level, campaign_id);

-- Жизненный цикл снимка — явное состояние, не время: building → complete | failed, только вперёд.
-- Пока building — пишутся строки; complete — запечатан (sealed_at), строки не добавляются и не меняются;
-- failed — сборка брошена, строки не добавляются. Меняются только status и sealed_at; удаляет только роль удаления.
CREATE FUNCTION snapshot_lifecycle() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF current_setting('app.deleting', true) = 'on' THEN  -- только внутри функции удаления
      RETURN OLD;
    END IF;
    RAISE EXCEPTION 'snapshots: DELETE is not allowed' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'building' THEN
      RAISE EXCEPTION 'snapshot must be created as building' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM sync_runs r WHERE r.id = NEW.sync_run_id AND r.workspace_id = NEW.workspace_id
                   AND r.status IN ('running', 'waiting_report', 'succeeded')) THEN
      RAISE EXCEPTION 'snapshot: sync_run % must be of the same workspace and not queued/failed/skipped',
        NEW.sync_run_id USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status <> 'building' OR NEW.status NOT IN ('complete', 'failed') THEN
    RAISE EXCEPTION 'snapshot % cannot move % → %', OLD.id, OLD.status, NEW.status
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF to_jsonb(NEW) - 'status' - 'sealed_at' <> to_jsonb(OLD) - 'status' - 'sealed_at' THEN
    RAISE EXCEPTION 'snapshot %: only status and sealed_at may change', OLD.id
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END
$$;
CREATE TRIGGER snapshots_lifecycle BEFORE INSERT OR UPDATE OR DELETE ON snapshots
  FOR EACH ROW EXECUTE FUNCTION snapshot_lifecycle();

-- Строки пишутся только в снимок в состоянии building. UPDATE/DELETE строк запрещены append-only триггером.
CREATE FUNCTION stat_rows_only_while_building() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM new_rows n JOIN snapshots s ON s.id = n.snapshot_id WHERE s.status <> 'building') THEN
    RAISE EXCEPTION 'snapshot is sealed: stat_rows can be added only while the snapshot is building'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NULL;
END
$$;
CREATE TRIGGER stat_rows_sealed AFTER INSERT ON stat_rows REFERENCING NEW TABLE AS new_rows
  FOR EACH STATEMENT EXECUTE FUNCTION stat_rows_only_while_building();

-- Аудит, замер результата и дайджест опираются только на завершённый снимок.
CREATE FUNCTION require_complete_snapshot() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.snapshot_id IS NOT NULL
     AND (SELECT status FROM snapshots WHERE id = NEW.snapshot_id) IS DISTINCT FROM 'complete' THEN
    RAISE EXCEPTION '%: snapshot % is not complete', TG_TABLE_NAME, NEW.snapshot_id
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END
$$;

-- Отдельный срок хранения: 60 дней (ARCHITECTURE.md §2.4).
CREATE TABLE search_query_texts (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id   bigint NOT NULL REFERENCES workspaces,
  text_hash      bytea NOT NULL CHECK (length(text_hash) = 32),
  text_sanitized text NOT NULL,
  first_seen_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, text_hash)
);
-- Срок хранения — отдельной строкой на каждое появление, чтобы таблица текстов оставалась append-only.
-- Текст удаляется, когда последнее появление старше 60 дней: max(seen_at) < now() - interval '60 days'.
CREATE TABLE search_query_sightings (
  query_id bigint NOT NULL REFERENCES search_query_texts,
  seen_on  date NOT NULL,  -- день из отчёта, в котором запрос встретился
  PRIMARY KEY (query_id, seen_on)
);

-- Аудит workspace на общий срез данных. Ключ идемпотентности — task_key задачи (как sync_run_id у синхронизации):
-- повтор той же задачи возвращает тот же аудит, новая задача — новый аудит (досинхронизация в 14:00 → новый аудит).
CREATE TABLE audit_runs (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id      bigint NOT NULL REFERENCES workspaces,
  release_id        bigint NOT NULL REFERENCES releases,
  kind              text NOT NULL CHECK (kind IN ('free', 'scheduled')),
  task_key          text NOT NULL UNIQUE CHECK (length(task_key) > 0),
  -- последний полный день данных; фиксируется до выборки снимков и не пересчитывается во время аудита
  data_cutoff       date NOT NULL,
  settings          jsonb NOT NULL CHECK (jsonb_typeof(settings) = 'object'),  -- замороженные настройки
  rules_run         text[] NOT NULL,
  -- «недостаточно данных» по правилам: [{account, rule, reason, object_type, object_id}]
  rules_skipped     jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(rules_skipped) = 'array'),
  -- аккаунты, не вошедшие в аудит: [{account, reason, detail}] — «участвовали 3 из 4, X недоступен: access_denied»
  excluded_accounts jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(excluded_accounts) = 'array'),
  created_at        timestamptz NOT NULL DEFAULT now()
);

-- Состав аудита: ровно один снимок на аккаунт, все — на data_cutoff аудита (разные дни не смешиваются).
CREATE TABLE audit_run_snapshots (
  audit_run_id      bigint NOT NULL REFERENCES audit_runs,
  direct_account_id bigint NOT NULL REFERENCES direct_accounts,
  snapshot_id       bigint NOT NULL REFERENCES snapshots,
  PRIMARY KEY (audit_run_id, direct_account_id)
);

CREATE FUNCTION check_audit_snapshot() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM snapshots s
    JOIN sync_runs r ON r.id = s.sync_run_id
    JOIN audit_runs a ON a.id = NEW.audit_run_id
    WHERE s.id = NEW.snapshot_id AND s.status = 'complete'
      AND r.direct_account_id = NEW.direct_account_id
      AND s.workspace_id = a.workspace_id
      AND s.period_to = a.data_cutoff) THEN
    RAISE EXCEPTION 'snapshot % does not fit audit %: must be complete, of this account and workspace, on data_cutoff',
      NEW.snapshot_id, NEW.audit_run_id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END
$$;
CREATE TRIGGER audit_run_snapshots_fit BEFORE INSERT ON audit_run_snapshots
  FOR EACH ROW EXECUTE FUNCTION check_audit_snapshot();

-- Жизненный цикл проблемы. Единственная изменяемая часть — закрытие.
-- issue_key = sha256(workspace_id|direct_account_id|issue_type|object_type|object_id|dimension)
CREATE TABLE issues (  -- [O]
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id      bigint NOT NULL REFERENCES workspaces,
  direct_account_id bigint NOT NULL REFERENCES direct_accounts,
  issue_key         bytea NOT NULL CHECK (length(issue_key) = 32),
  issue_type        text NOT NULL,  -- семейство правила без версии: high_cpa, zero_conv_campaign, …
  object_type       text NOT NULL,
  object_id         bigint NOT NULL,
  dimension         text NOT NULL DEFAULT '',
  opened_at         timestamptz NOT NULL DEFAULT now(),
  closed_at         timestamptz,
  close_reason      text CHECK (close_reason IN ('resolved', 'measured')),
  CHECK ((closed_at IS NULL) = (close_reason IS NULL))
);
-- Одна открытая проблема (а значит, одна открытая рекомендация) на ключ.
CREATE UNIQUE INDEX issues_one_open ON issues (issue_key) WHERE closed_at IS NULL;

CREATE TABLE findings (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  audit_run_id bigint NOT NULL REFERENCES audit_runs,
  issue_id     bigint NOT NULL REFERENCES issues,
  rule_version text NOT NULL CHECK (rule_version ~ '^[a-z0-9_]+@[0-9]+$'),
  lost         jsonb NOT NULL CHECK (value_is_valid(lost)),
  recoverable  jsonb NOT NULL CHECK (value_is_valid(recoverable)),
  -- достаточность данных текущего периода (current_data_quality), не статистическая уверенность
  data_quality text NOT NULL CHECK (data_quality IN ('high', 'medium', 'low')),
  evidence     jsonb NOT NULL CHECK (evidence_is_valid(evidence)),
  evidence_meta jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(evidence_meta) = 'object'),
  action       jsonb NOT NULL CHECK (jsonb_typeof(action) = 'object' AND action ? 'type'),
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (audit_run_id, issue_id),
  UNIQUE (id, issue_id)  -- цель составных FK: вывод принадлежит конкретной проблеме
);

CREATE TABLE explanations (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  finding_id  bigint NOT NULL REFERENCES findings,
  source      text NOT NULL CHECK (source IN ('llm', 'template')),
  provider    text,
  model       text,
  prompt_hash bytea,
  text        text NOT NULL CHECK (length(text) > 0),
  release_id  bigint NOT NULL REFERENCES releases,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, finding_id),
  CHECK ((source = 'llm') = (provider IS NOT NULL AND model IS NOT NULL AND prompt_hash IS NOT NULL))
);

CREATE TABLE recommendations (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  issue_id       bigint NOT NULL UNIQUE REFERENCES issues,  -- одна рекомендация на жизненный цикл проблемы
  finding_id     bigint NOT NULL UNIQUE,
  explanation_id bigint NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, issue_id),
  -- вывод принадлежит той же проблеме, что и рекомендация
  FOREIGN KEY (finding_id, issue_id) REFERENCES findings (id, issue_id),
  -- объяснение обязательно относится к тому же выводу
  FOREIGN KEY (explanation_id, finding_id) REFERENCES explanations (id, finding_id)
);

-- Идентичность объектов в событиях и результатах — реляционная (составные FK), не JSON.
-- issue_id в обеих таблицах заполняется триггером из recommendations и проверяется FK.
-- results создаётся раньше events: события 'measured' ссылаются на результат.
CREATE TABLE recommendation_results (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  recommendation_id bigint NOT NULL UNIQUE,
  issue_id          bigint NOT NULL,
  finding_id        bigint NOT NULL,  -- какая именно версия действия (-15% или -25%) замерена
  measurement_id    bigint NOT NULL UNIQUE,  -- заполняет триггер: замер последнего 'done'; FK — после measurements
  snapshot_id       bigint REFERENCES snapshots,  -- NULL только у insufficient: данных за окно так и не пришло
  release_id        bigint NOT NULL REFERENCES releases,
  before            jsonb NOT NULL CHECK (evidence_is_valid(before)),
  after             jsonb NOT NULL CHECK (evidence_is_valid(after)),
  saved             jsonb CHECK (saved IS NULL OR (value_is_valid(saved) AND saved->>'calculation_type' = 'estimated')),
  verdict           text NOT NULL CHECK (verdict IN ('effect', 'no_effect', 'not_confirmed', 'insufficient')),
  -- наблюдаемое изменение и причина вердикта (cpa_change_pct, conversions_change_pct, reason); saved — отдельно
  effect            jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(effect) = 'object'),
  created_at        timestamptz NOT NULL DEFAULT now(),
  CHECK (snapshot_id IS NOT NULL OR verdict = 'insufficient'),
  UNIQUE (id, recommendation_id, finding_id),
  FOREIGN KEY (recommendation_id, issue_id) REFERENCES recommendations (id, issue_id),
  FOREIGN KEY (finding_id, issue_id) REFERENCES findings (id, issue_id),
  -- «Сэкономлено» есть только при эффекте
  CHECK ((verdict = 'effect') = (saved IS NOT NULL))
);

CREATE TABLE recommendation_events (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  recommendation_id bigint NOT NULL,
  issue_id          bigint NOT NULL,
  type              text NOT NULL CHECK (type IN (
                      -- действия человека
                      'postponed', 'rejected', 'done',
                      -- системные
                      'unpostponed', 'seen_again', 'resolved', 'measured', 'measurement_skipped')),
  actor_user_id     bigint REFERENCES users,
  finding_id        bigint,  -- seen_again: новый вывод · done: выполненная версия · measured: замеренная версия
  explanation_id    bigint,  -- seen_again: объяснение к новому выводу
  result_id         bigint,  -- measured
  payload           jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(payload) = 'object'),
  -- done: календарный день выполнения в часовом поясе данных. Считает приложение по имени пояса (ZoneInfo),
  -- БД смещений не знает; ±1 день от UTC-даты — любой реальный пояс, защита от задним числом.
  execution_date    date,
  created_at        timestamptz NOT NULL DEFAULT now(),
  CHECK ((type = 'done') = (execution_date IS NOT NULL)),
  CHECK (execution_date BETWEEN (created_at AT TIME ZONE 'UTC')::date - 1 AND (created_at AT TIME ZONE 'UTC')::date + 1),
  FOREIGN KEY (recommendation_id, issue_id) REFERENCES recommendations (id, issue_id),
  -- вывод принадлежит той же проблеме, что и рекомендация
  FOREIGN KEY (finding_id, issue_id) REFERENCES findings (id, issue_id),
  FOREIGN KEY (explanation_id, finding_id) REFERENCES explanations (id, finding_id),
  -- результат — этой же рекомендации и именно той версии действия
  FOREIGN KEY (result_id, recommendation_id, finding_id)
    REFERENCES recommendation_results (id, recommendation_id, finding_id),
  -- действия человека — только с автором; системные — только без
  CHECK ((type IN ('postponed', 'rejected', 'done')) = (actor_user_id IS NOT NULL)),
  CHECK (type <> 'postponed' OR payload ? 'until'),
  -- пересчёт: новый неизменяемый вывод и объяснение к нему; UI показывает последний
  CHECK ((type = 'seen_again') = (explanation_id IS NOT NULL)),
  -- человек выполнил конкретную версию действия (-15% или -25%) — именно её потом и замеряем
  CHECK ((type IN ('seen_again', 'done', 'measured')) = (finding_id IS NOT NULL)),
  CHECK ((type = 'measured') = (result_id IS NOT NULL))
);
CREATE INDEX recommendation_events_current ON recommendation_events (recommendation_id, id DESC);

-- Замер выполненной рекомендации (ARCHITECTURE.md §5). Создаётся самой БД в момент 'done' — окна и методика
-- фиксируются тогда и не пересчитываются: «Сэкономлено» воспроизводимо из done → finding → окна →
-- доказательства без обращения к текущим настройкам клиента. Определение конверсии здесь не копируется: оно берётся
-- из снимка выполненного вывода (finding → audit_run_snapshots → snapshots), все звенья append-only — разойтись
-- с выполненным выводом оно не может. Один 'done' — один замер; цикл проблемы — своя
-- рекомендация и свой результат, поэтому повторное появление проблемы не наследует старый замер.
CREATE TABLE measurements (
  id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  done_event_id         bigint NOT NULL UNIQUE REFERENCES recommendation_events,
  recommendation_id     bigint NOT NULL,
  issue_id              bigint NOT NULL,
  finding_id            bigint NOT NULL,          -- выполненная версия действия (−15% или −25%)
  policy                text NOT NULL CHECK (policy ~ '^[a-z0-9_]+@[0-9]+$'),  -- методика замера и её версия
  before_from           date NOT NULL,
  before_to             date NOT NULL,
  after_from            date NOT NULL,
  after_to              date NOT NULL,
  created_at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, recommendation_id, finding_id),
  FOREIGN KEY (recommendation_id, issue_id) REFERENCES recommendations (id, issue_id),
  FOREIGN KEY (finding_id, issue_id) REFERENCES findings (id, issue_id),
  CHECK (before_from <= before_to AND before_to < after_from AND after_from <= after_to)
);

-- День выполнения — execution_date события 'done' (его считает приложение в часовом поясе данных).
-- measure@2 (текущая; @1 — только для уже созданных замеров): 7 дней до дня выполнения и 7 дней после; сам день выполнения не входит ни в одно окно.
CREATE FUNCTION create_measurement_on_done() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE d date := NEW.execution_date;
BEGIN
  INSERT INTO measurements (done_event_id, recommendation_id, issue_id, finding_id, policy,
                            before_from, before_to, after_from, after_to)
  SELECT NEW.id, NEW.recommendation_id, NEW.issue_id, NEW.finding_id, i.issue_type || '_measure@2',
         d - 7, d - 1, d + 1, d + 7
  FROM issues i
  WHERE i.id = NEW.issue_id;
  RETURN NULL;
END
$$;
CREATE TRIGGER recommendation_events_measurement AFTER INSERT ON recommendation_events
  FOR EACH ROW WHEN (NEW.type = 'done') EXECUTE FUNCTION create_measurement_on_done();

-- Результат — замер последнего 'done' (как и finding_id результата, см. check_result_matches_done).
CREATE FUNCTION fill_measurement_of_result() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.measurement_id := (SELECT m.id FROM measurements m JOIN recommendation_events e ON e.id = m.done_event_id
                         WHERE e.recommendation_id = NEW.recommendation_id ORDER BY e.id DESC LIMIT 1);
  RETURN NEW;
END
$$;
CREATE TRIGGER recommendation_results_measurement BEFORE INSERT ON recommendation_results
  FOR EACH ROW EXECUTE FUNCTION fill_measurement_of_result();
-- результат — именно этого замера, этой рекомендации и той версии действия, которую выполнили
ALTER TABLE recommendation_results ADD FOREIGN KEY (measurement_id, recommendation_id, finding_id)
  REFERENCES measurements (id, recommendation_id, finding_id);


CREATE FUNCTION fill_issue_from_recommendation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.issue_id := (SELECT issue_id FROM recommendations WHERE id = NEW.recommendation_id);
  RETURN NEW;
END
$$;
CREATE TRIGGER recommendation_events_issue BEFORE INSERT ON recommendation_events
  FOR EACH ROW EXECUTE FUNCTION fill_issue_from_recommendation();
CREATE TRIGGER recommendation_results_issue BEFORE INSERT ON recommendation_results
  FOR EACH ROW EXECUTE FUNCTION fill_issue_from_recommendation();

-- 'done' — только над версией действия, которую человеку показывали: исходной или пришедшей через seen_again.
CREATE FUNCTION check_done_finding_was_shown() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.type = 'done' AND NEW.finding_id IS NOT NULL AND NOT (
       EXISTS (SELECT 1 FROM recommendations WHERE id = NEW.recommendation_id AND finding_id = NEW.finding_id)
    OR EXISTS (SELECT 1 FROM recommendation_events WHERE recommendation_id = NEW.recommendation_id
                 AND type = 'seen_again' AND finding_id = NEW.finding_id)) THEN
    RAISE EXCEPTION 'finding % was never shown for recommendation %', NEW.finding_id, NEW.recommendation_id
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END
$$;
CREATE TRIGGER recommendation_events_done_shown BEFORE INSERT ON recommendation_events
  FOR EACH ROW EXECUTE FUNCTION check_done_finding_was_shown();

-- Замер — только над тем, что человек выполнил: finding результата = finding последнего 'done'.
CREATE FUNCTION check_result_matches_done() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.finding_id IS DISTINCT FROM (SELECT finding_id FROM recommendation_events
                                      WHERE recommendation_id = NEW.recommendation_id AND type = 'done'
                                      ORDER BY id DESC LIMIT 1) THEN
    RAISE EXCEPTION 'result finding % is not the finding marked done for recommendation %',
      NEW.finding_id, NEW.recommendation_id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END
$$;
CREATE TRIGGER recommendation_results_done BEFORE INSERT ON recommendation_results
  FOR EACH ROW EXECUTE FUNCTION check_result_matches_done();

-- ============================================================================
-- Транзакционный outbox
-- ============================================================================
-- Доменное событие пишется в той же транзакции, что и бизнес-изменение; доставка наружу (Telegram, email, UI) —
-- отдельным воркером после COMMIT. Никаких HTTP внутри транзакции БД.
-- Состояние — из полей доставки, без изменяемого status: delivered_at задан → доставлено; locked_until в будущем
-- → в работе (аренда воркера); last_error → ошибка, повтор не раньше available_at. Доставка at-least-once:
-- получатель обязан быть идемпотентным по id события.
CREATE TABLE outbox_events (  -- [O]
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id   bigint NOT NULL REFERENCES workspaces,
  event_type     text NOT NULL CHECK (event_type ~ '^[a-z_]+$'),
  aggregate_type text NOT NULL CHECK (aggregate_type ~ '^[a-z_]+$'),
  aggregate_id   bigint NOT NULL,
  -- только ID и числа: без текстов запросов, названий, ПД (то же правило, что для промпта LLM)
  payload        jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(payload) = 'object'),
  created_at     timestamptz NOT NULL DEFAULT now(),
  available_at   timestamptz NOT NULL DEFAULT now(),
  attempts       integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  locked_until   timestamptz,
  delivered_at   timestamptz,
  last_error     text CHECK (last_error ~ '^[a-z_]+$'),
  CHECK (delivered_at IS NULL OR locked_until IS NULL)
);
CREATE INDEX outbox_events_pending ON outbox_events (available_at, id) WHERE delivered_at IS NULL;

-- ============================================================================
-- Дайджесты и уведомления
-- ============================================================================

CREATE TABLE digests (  -- [A]
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id bigint NOT NULL REFERENCES workspaces,
  kind         text NOT NULL CHECK (kind IN ('daily', 'weekly')),
  snapshot_id  bigint NOT NULL REFERENCES snapshots,
  audit_run_id bigint NOT NULL REFERENCES audit_runs,
  payload      jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE notifications (  -- [O]
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id bigint NOT NULL REFERENCES workspaces,
  kind         text NOT NULL CHECK (kind IN ('digest', 'correction', 'new_problem', 'critical', 'billing')),
  channel      text NOT NULL CHECK (channel IN ('telegram', 'email')),
  dedup_key    text NOT NULL UNIQUE,
  digest_id    bigint REFERENCES digests,
  snapshot_id  bigint REFERENCES snapshots,
  payload      jsonb NOT NULL DEFAULT '{}',
  status       text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'sent', 'failed', 'skipped')),
  attempts     smallint NOT NULL DEFAULT 0,
  created_at   timestamptz NOT NULL DEFAULT now(),
  sent_at      timestamptz,
  CHECK ((status = 'sent') = (sent_at IS NOT NULL)),
  CHECK (kind <> 'digest' OR digest_id IS NOT NULL)
);
CREATE INDEX notifications_queue ON notifications (created_at) WHERE status = 'queued';

-- ============================================================================
-- Биллинг
-- ============================================================================

CREATE TABLE subscriptions (  -- [O]
  id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id         bigint NOT NULL REFERENCES workspaces,
  plan                 text NOT NULL CHECK (plan IN ('start', 'business', 'business_plus')),
  status               text NOT NULL CHECK (status IN ('active', 'past_due', 'canceled', 'expired')),
  price                numeric(12, 2) NOT NULL CHECK (price > 0),
  current_period_start timestamptz NOT NULL,
  current_period_end   timestamptz NOT NULL,
  auto_renew           boolean NOT NULL DEFAULT false,
  renew_consent_at     timestamptz,
  payment_method_ref   text,  -- токен провайдера; данные карты не храним
  canceled_at          timestamptz,
  CHECK (current_period_end > current_period_start),
  -- автопродление только с явным согласием и сохранённым способом оплаты
  CHECK (NOT auto_renew OR (renew_consent_at IS NOT NULL AND payment_method_ref IS NOT NULL)),
  -- отменённая или истёкшая подписка не продлевается
  CHECK (status NOT IN ('canceled', 'expired') OR NOT auto_renew),
  CHECK (status <> 'canceled' OR canceled_at IS NOT NULL)
);
CREATE UNIQUE INDEX subscriptions_one_active
  ON subscriptions (workspace_id) WHERE status IN ('active', 'past_due', 'canceled');

CREATE TABLE subscription_events (  -- [A]
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  subscription_id bigint NOT NULL REFERENCES subscriptions,
  type            text NOT NULL CHECK (type IN ('created', 'paid', 'renewal_reminder_sent', 'renewed',
                                                'renewal_failed', 'canceled', 'expired')),
  payload         jsonb NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE payments (  -- [O]
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  subscription_id     bigint REFERENCES subscriptions,  -- NULL: платёж пришёл для удалённого workspace
  provider            text NOT NULL CHECK (provider IN ('yookassa')),
  provider_payment_id text NOT NULL UNIQUE,  -- идемпотентность webhook
  amount              numeric(12, 2) NOT NULL CHECK (amount > 0),
  status              text NOT NULL CHECK (status IN ('pending', 'succeeded', 'canceled', 'refunded')),
  receipt_ref         text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

-- HMAC-SHA256 логина рекламного аккаунта с секретом вне БД. Без ссылок — переживает удаление аккаунта.
CREATE TABLE free_audit_claims (  -- [A]
  direct_account_hash bytea PRIMARY KEY CHECK (length(direct_account_hash) = 32),
  claimed_at          timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- Удаление данных  [O]; workspace_id без FK — запись переживает удалённый workspace
-- ============================================================================

CREATE TABLE deletion_requests (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id bigint,
  requested_by text NOT NULL CHECK (requested_by ~ '^(user|operator):[0-9]+$' OR requested_by = 'system:retention'),
  scope        text NOT NULL CHECK (scope IN ('workspace', 'search_query_texts_expired', 'unreferenced_snapshots')),
  status       text NOT NULL DEFAULT 'requested'
               CHECK (status IN ('requested', 'scheduled', 'deleting', 'verified', 'completed', 'failed')),
  requested_at timestamptz NOT NULL DEFAULT now(),
  started_at   timestamptz,
  completed_at timestamptz,
  verification jsonb,
  deleted_by   text CHECK (deleted_by ~ '^[a-z_]+(@[a-z_]+)?$'),  -- роль/процесс, без ПД: deleter@worker
  CHECK (scope <> 'workspace' OR workspace_id IS NOT NULL),
  CHECK (status NOT IN ('verified', 'completed') OR verification IS NOT NULL),
  CHECK ((status = 'completed') = (completed_at IS NOT NULL))
);

-- Удаление всех данных workspace. Единственное место, где записан порядок удаления (он же — порядок FK).
-- Вызывается ролью app_deleter из процесса deletion_request — у роли нет никаких прав на таблицы, только EXECUTE
-- этой функции: SECURITY DEFINER, search_path зафиксирован. Отметка бесплатного аудита (free_audit_claims, HMAC
-- без ПД) намеренно переживает удаление — исключение политики хранения (ARCHITECTURE.md §2.5).
-- Возвращает число удалённых строк по таблицам —
-- это и есть содержимое deletion_requests.verification. Платежи обезличиваются, а не удаляются (бухучёт).
CREATE FUNCTION delete_workspace_data(ws bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  counts jsonb := '{}';
  n bigint;
  sole_users bigint[];
BEGIN
  PERFORM pg_advisory_xact_lock(ws);  -- ждёт записи снимков/аудитов, не пускает новые (DATA_MODEL.md §9.2)
  PERFORM set_config('app.deleting', 'on', true);
  IF (SELECT status FROM workspaces WHERE id = ws) IS DISTINCT FROM 'deletion_pending' THEN
    RAISE EXCEPTION 'workspace % is not in deletion_pending', ws;
  END IF;

  SELECT coalesce(array_agg(m.user_id), '{}') INTO sole_users
  FROM memberships m
  WHERE m.workspace_id = ws
    AND NOT EXISTS (SELECT 1 FROM memberships o WHERE o.user_id = m.user_id AND o.workspace_id <> ws);

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
  DELETE FROM memberships WHERE workspace_id = ws;
  DELETE FROM workspaces WHERE id = ws;
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('workspaces', n);

  DELETE FROM sessions WHERE user_id = ANY (sole_users);
  DELETE FROM telegram_links WHERE user_id = ANY (sole_users);
  DELETE FROM yandex_identities WHERE user_id = ANY (sole_users);
  DELETE FROM users WHERE id = ANY (sole_users);
  GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('users', n);

  PERFORM set_config('app.deleting', 'off', true);
  RETURN counts;
END $$;

-- Срок хранения текстов поисковых запросов — 60 дней от последнего появления в отчёте (ARCHITECTURE.md §2.4).
-- Удаляет пачку текстов, чьё последнее появление раньше cutoff (дату считает вызывающий в часовом поясе данных —
-- результат не зависит от часового пояса сервера). Агрегаты stat_rows остаются: у них нет FK на текст.
-- Каждая непустая пачка — запись deletion_requests (system:retention). Повторный вызов безопасен.
CREATE FUNCTION purge_search_query_texts(cutoff date, batch_size integer) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  ids bigint[];
  n integer;
BEGIN
  IF batch_size NOT BETWEEN 1 AND 10000 THEN
    RAISE EXCEPTION 'batch_size must be 1..10000';
  END IF;
  SELECT array_agg(query_id) INTO ids FROM (
    SELECT query_id FROM search_query_sightings GROUP BY query_id HAVING max(seen_on) < cutoff
    ORDER BY query_id LIMIT batch_size) expired;
  IF ids IS NULL THEN
    RETURN 0;
  END IF;
  PERFORM set_config('app.deleting', 'on', true);
  DELETE FROM search_query_sightings WHERE query_id = ANY (ids);
  DELETE FROM search_query_texts WHERE id = ANY (ids);
  GET DIAGNOSTICS n = ROW_COUNT;
  PERFORM set_config('app.deleting', 'off', true);
  INSERT INTO deletion_requests (requested_by, scope, status, started_at, completed_at, verification, deleted_by)
  VALUES ('system:retention', 'search_query_texts_expired', 'completed', now(), now(),
          jsonb_build_object('search_query_texts', n, 'cutoff', cutoff), 'purge_search_query_texts');
  RETURN n;
END $$;

-- ============================================================================
-- Append-only триггеры
-- ============================================================================

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY array['releases', 'stat_rows', 'search_query_texts', 'search_query_sightings',
                           'audit_runs', 'audit_run_snapshots', 'findings', 'explanations', 'recommendations',
                           'measurements',
                           'recommendation_events', 'recommendation_results', 'digests',
                           'subscription_events', 'free_audit_claims']
  LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I
                    FOR EACH ROW EXECUTE FUNCTION forbid_mutation()', t || '_append_only', t);
  END LOOP;
END $$;

CREATE TRIGGER recommendation_results_complete_snapshot BEFORE INSERT ON recommendation_results
  FOR EACH ROW EXECUTE FUNCTION require_complete_snapshot();
CREATE TRIGGER digests_complete_snapshot BEFORE INSERT ON digests
  FOR EACH ROW EXECUTE FUNCTION require_complete_snapshot();

-- ============================================================================
-- Целостность между таблицами и жизненные циклы (ревью схемы)
-- ============================================================================

-- Все ссылки строки — внутри одного workspace. Иначе строка чужого workspace держит FK, и законное удаление
-- (delete_workspace_data) навсегда падает на внешнем ключе.
CREATE FUNCTION check_same_workspace() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE ok boolean := true;
BEGIN
  IF TG_TABLE_NAME = 'sync_runs' THEN
    ok := EXISTS (SELECT 1 FROM direct_accounts a JOIN direct_connections c ON c.id = a.direct_connection_id
                  WHERE a.id = NEW.direct_account_id AND c.workspace_id = NEW.workspace_id)
      AND (NEW.metrika_counter_id IS NULL OR EXISTS (
            SELECT 1 FROM metrika_counters mc JOIN metrika_connections m ON m.id = mc.metrika_connection_id
            WHERE mc.id = NEW.metrika_counter_id AND m.workspace_id = NEW.workspace_id));
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
CREATE TRIGGER sync_runs_same_workspace BEFORE INSERT OR UPDATE ON sync_runs
  FOR EACH ROW EXECUTE FUNCTION check_same_workspace();
CREATE TRIGGER issues_same_workspace BEFORE INSERT ON issues
  FOR EACH ROW EXECUTE FUNCTION check_same_workspace();
CREATE TRIGGER digests_same_workspace BEFORE INSERT ON digests
  FOR EACH ROW EXECUTE FUNCTION check_same_workspace();
CREATE TRIGGER notifications_same_workspace BEFORE INSERT OR UPDATE ON notifications
  FOR EACH ROW EXECUTE FUNCTION check_same_workspace();
-- после fill_issue_from_recommendation: имена триггеров срабатывают по алфавиту, issue_id уже заполнен
CREATE TRIGGER recommendation_results_zz_same_workspace BEFORE INSERT ON recommendation_results
  FOR EACH ROW EXECUTE FUNCTION check_same_workspace();

-- sync_run: только вперёд, завершённый неизменен, идентичность (чей, какого аккаунта, какой счётчик) заморожена.
-- queued → running | skipped | failed; running ⇄ waiting_report → succeeded | failed | skipped.
CREATE FUNCTION sync_run_lifecycle() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status IN ('succeeded', 'failed', 'skipped') THEN
    RAISE EXCEPTION 'sync_run % is finished (%)', OLD.id, OLD.status USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.workspace_id, NEW.direct_account_id, NEW.metrika_counter_id, NEW.kind)
     IS DISTINCT FROM (OLD.workspace_id, OLD.direct_account_id, OLD.metrika_counter_id, OLD.kind)
     OR (NEW.status = 'queued' AND OLD.status <> 'queued') THEN
    RAISE EXCEPTION 'sync_run %: identity is frozen and status moves only forward', OLD.id
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END
$$;
CREATE TRIGGER sync_runs_lifecycle BEFORE UPDATE ON sync_runs
  FOR EACH ROW EXECUTE FUNCTION sync_run_lifecycle();

-- issue: единственное изменение — закрытие, один раз. Переоткрытие = новая строка (DATA_MODEL.md §4).
CREATE FUNCTION issue_close_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.closed_at IS NOT NULL
     OR to_jsonb(NEW) - 'closed_at' - 'close_reason' <> to_jsonb(OLD) - 'closed_at' - 'close_reason' THEN
    RAISE EXCEPTION 'issue %: only closing an open issue is allowed', OLD.id
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END
$$;
CREATE TRIGGER issues_close_only BEFORE UPDATE ON issues
  FOR EACH ROW EXECUTE FUNCTION issue_close_only();

-- ============================================================================
-- OAuth-токены: приложение не видит шифротекст (column-level GRANT), работает через функции
-- ============================================================================
-- Писать и сбрасывать токен может приложение (OAuth-колбэк, отключение); читать — только роль воркера app_token.
-- Функции SECURITY DEFINER с фиксированным search_path, подключение ищется строго в пределах переданного workspace.

CREATE FUNCTION set_connection_token(kind text, ws bigint, connection bigint, token bytea, expires timestamptz)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE n integer;
BEGIN
  IF token IS NULL OR length(token) = 0 THEN
    RAISE EXCEPTION 'token is empty';
  END IF;
  IF kind = 'direct' THEN
    UPDATE direct_connections SET token_enc = token, token_expires_at = expires, status = 'connected',
           status_detail = NULL, status_changed_at = now()
     WHERE id = connection AND workspace_id = ws;
  ELSIF kind = 'metrika' THEN
    UPDATE metrika_connections SET token_enc = token, token_expires_at = expires, status = 'connected',
           status_detail = NULL, status_changed_at = now()
     WHERE id = connection AND workspace_id = ws;
  ELSE
    RAISE EXCEPTION 'kind must be direct or metrika';
  END IF;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN
    RAISE EXCEPTION 'connection % not found in workspace %', connection, ws USING ERRCODE = 'no_data_found';
  END IF;
END $$;

-- disconnected — пользователь отключил; token_revoked — отозван у Яндекса. Токен удаляется в обоих случаях.
-- Отключение пользователем окончательно: token_revoked не перезаписывает disconnected.
CREATE FUNCTION drop_connection_token(kind text, ws bigint, connection bigint, new_status text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF new_status NOT IN ('disconnected', 'token_revoked') THEN
    RAISE EXCEPTION 'new_status must be disconnected or token_revoked';
  END IF;
  IF kind = 'direct' THEN
    UPDATE direct_connections
       SET status_changed_at = CASE WHEN status <> new_status THEN now() ELSE status_changed_at END,
           status = new_status, token_enc = NULL, token_expires_at = NULL
     WHERE id = connection AND workspace_id = ws AND (new_status = 'disconnected' OR status <> 'disconnected');
  ELSIF kind = 'metrika' THEN
    UPDATE metrika_connections
       SET status_changed_at = CASE WHEN status <> new_status THEN now() ELSE status_changed_at END,
           status = new_status, token_enc = NULL, token_expires_at = NULL
     WHERE id = connection AND workspace_id = ws AND (new_status = 'disconnected' OR status <> 'disconnected');
  ELSE
    RAISE EXCEPTION 'kind must be direct or metrika';
  END IF;
END $$;

CREATE FUNCTION connection_token(kind text, ws bigint, connection bigint)
RETURNS bytea LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE t bytea;
BEGIN
  IF kind = 'direct' THEN
    SELECT token_enc INTO t FROM direct_connections WHERE id = connection AND workspace_id = ws;
  ELSIF kind = 'metrika' THEN
    SELECT token_enc INTO t FROM metrika_connections WHERE id = connection AND workspace_id = ws;
  ELSE
    RAISE EXCEPTION 'kind must be direct or metrika';
  END IF;
  IF t IS NULL THEN
    RAISE EXCEPTION 'no token for connection % in workspace %', connection, ws USING ERRCODE = 'no_data_found';
  END IF;
  RETURN t;
END $$;

-- ============================================================================
-- Права
-- ============================================================================

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
-- В PostgreSQL ≤ 14 PUBLIC по умолчанию может создавать объекты в public — у приложения не должно быть DDL.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Приложение: читать всё, добавлять везде, изменять — только операционные таблицы. Без DELETE, без DDL.
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO app_rw;
GRANT UPDATE ON users, workspaces, memberships, workspace_settings, telegram_links,
                direct_accounts, metrika_counters,
                sync_runs, snapshots, issues, notifications, outbox_events, subscriptions, payments,
                deletion_requests
             TO app_rw;
-- Сессии и привязки Telegram — служебные, не доказательные: выход из аккаунта удаляет строку.
GRANT DELETE ON sessions, telegram_links TO app_rw;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_rw;

-- Подключения: всё, кроме шифротекста токена. SELECT * по этим таблицам приложению недоступен — только перечисленные
-- столбцы; токен пишется и сбрасывается функциями, читается — только ролью воркера app_token.
REVOKE SELECT, INSERT ON direct_connections, metrika_connections FROM app_rw;
GRANT SELECT (id, workspace_id, yandex_login, token_expires_at, scopes, status, status_detail, status_changed_at,
              last_sync_at, has_token, last_success_at, last_error, last_error_at)
  ON direct_connections, metrika_connections TO app_rw;
GRANT INSERT (workspace_id, yandex_login, scopes, status, status_detail) ON direct_connections, metrika_connections
  TO app_rw;
GRANT UPDATE (status, status_detail, status_changed_at, last_sync_at, last_success_at, last_error, last_error_at, scopes)
  ON direct_connections, metrika_connections TO app_rw;
REVOKE EXECUTE ON FUNCTION set_connection_token(text, bigint, bigint, bytea, timestamptz),
                           drop_connection_token(text, bigint, bigint, text),
                           connection_token(text, bigint, bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION set_connection_token(text, bigint, bigint, bytea, timestamptz),
                          drop_connection_token(text, bigint, bigint, text) TO app_rw;
-- app_token = app_rw + чтение токена (членство GRANT app_rw TO app_token — на уровне кластера, как и сами роли).
GRANT EXECUTE ON FUNCTION connection_token(text, bigint, bigint) TO app_token;

-- Удаление: никаких прав на таблицы — только вызов функций удаления (SECURITY DEFINER).
REVOKE EXECUTE ON FUNCTION delete_workspace_data(bigint) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION purge_search_query_texts(date, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION delete_workspace_data(bigint) TO app_deleter;
GRANT EXECUTE ON FUNCTION purge_search_query_texts(date, integer) TO app_deleter;

-- Таблицы из будущих миграций получают те же базовые права автоматически. Удаление их данных
-- delete_workspace_data само не узнает: новую таблицу с workspace нужно добавить в функцию и в test_lifecycle.
ALTER DEFAULT PRIVILEGES FOR ROLE app_migrator IN SCHEMA public GRANT SELECT, INSERT ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE app_migrator IN SCHEMA public GRANT USAGE ON SEQUENCES TO app_rw;

