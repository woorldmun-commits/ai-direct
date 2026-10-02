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
  provider_request_id text CHECK (provider_request_id ~ '^[0-9A-Za-z-]{1,64}$'),  -- RequestId Яндекса при отказе API
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
  lost         jsonb NOT NULL CHECK (value_is_valid(lost) AND coalesce(lost->>'amount', '') NOT LIKE '-%'),
  recoverable  jsonb NOT NULL CHECK (value_is_valid(recoverable) AND coalesce(recoverable->>'amount', '') NOT LIKE '-%'),
  -- достаточность данных текущего периода (current_data_quality), не статистическая уверенность
  data_quality text NOT NULL CHECK (data_quality IN ('high', 'medium', 'low')),
  evidence     jsonb NOT NULL CHECK (evidence_is_valid(evidence)),
  evidence_meta jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(evidence_meta) = 'object'),
  action       jsonb NOT NULL CHECK (jsonb_typeof(action) = 'object' AND action ? 'type'),  -- кандидат от правила
  -- Политика безопасности (app/audit/policy.py): какой уровень действие требует и какой разрешён.
  -- inspect_only < review < change; политика только понижает, причина понижения — в policy_reasons.
  safety_policy   text NOT NULL CHECK (safety_policy ~ '^[a-z0-9_]+@[0-9]+$'),
  candidate_level text NOT NULL CHECK (candidate_level IN ('inspect_only', 'review', 'change')),
  action_level    text NOT NULL CHECK (action_level IN ('inspect_only', 'review', 'change')),
  policy_reasons  text[] NOT NULL DEFAULT '{}',
  CHECK (array_position(array['inspect_only', 'review', 'change'], action_level)
         <= array_position(array['inspect_only', 'review', 'change'], candidate_level)),
  CHECK ((action_level = candidate_level) = (cardinality(policy_reasons) = 0)),
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
  saved             jsonb CHECK (saved IS NULL OR (value_is_valid(saved) AND saved->>'calculation_type' = 'estimated'
                                       AND coalesce(saved->>'amount', '') NOT LIKE '-%')),
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
                      -- действия человека: done — «Я сделал это» (review/change); checked — «Проверил» (inspect_only:
                      -- изменений в рекламе не было, поэтому и замера «Сэкономлено» нет); rejected — «Не буду»
                      'postponed', 'rejected', 'done', 'checked',
                      -- системные
                      'unpostponed', 'seen_again', 'resolved', 'measured', 'measurement_skipped')),
  actor_user_id     bigint REFERENCES users,
  finding_id        bigint,  -- seen_again: новый вывод · done: выполненная версия · checked: проверенная · measured: замеренная
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
  CHECK ((type IN ('postponed', 'rejected', 'done', 'checked')) = (actor_user_id IS NOT NULL)),
  CHECK (type <> 'postponed' OR payload ? 'until'),
  -- пересчёт: новый неизменяемый вывод и объяснение к нему; UI показывает последний
  CHECK ((type = 'seen_again') = (explanation_id IS NOT NULL)),
  -- человек выполнил конкретную версию действия (-15% или -25%) — именно её потом и замеряем
  CHECK ((type IN ('seen_again', 'done', 'checked', 'measured')) = (finding_id IS NOT NULL)),
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

-- 'done' и 'checked' — только над версией действия, которую человеку показывали: исходной или пришедшей через
-- seen_again. И только по уровню, который разрешила политика безопасности (ARCHITECTURE.md §4.1):
-- inspect_only → только checked (менять ничего не советовали — «сделал» невозможно, замера не будет);
-- review / change → только done.
CREATE FUNCTION check_done_finding_was_shown() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE level text;
BEGIN
  IF NEW.type NOT IN ('done', 'checked') OR NEW.finding_id IS NULL THEN
    RETURN NEW;
  END IF;
  IF NOT (
       EXISTS (SELECT 1 FROM recommendations WHERE id = NEW.recommendation_id AND finding_id = NEW.finding_id)
    OR EXISTS (SELECT 1 FROM recommendation_events WHERE recommendation_id = NEW.recommendation_id
                 AND type = 'seen_again' AND finding_id = NEW.finding_id)) THEN
    RAISE EXCEPTION 'finding % was never shown for recommendation %', NEW.finding_id, NEW.recommendation_id
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT action_level INTO level FROM findings WHERE id = NEW.finding_id;
  IF (NEW.type = 'done') = (level = 'inspect_only') THEN
    RAISE EXCEPTION '% is not allowed for finding % with action level %', NEW.type, NEW.finding_id, level
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

