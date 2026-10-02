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
  scope        text NOT NULL CHECK (scope IN ('workspace', 'search_query_texts_expired', 'unreferenced_snapshots',
                                     'personal_data_expired')),
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
-- Последний workspace организации уносит с собой организацию, её участников и пользователей, у которых других
-- организаций нет (как раньше — пользователей без других workspace). Принятия документов (legal_acceptances,
-- в т.ч. мандаты агентства) остаются как доказательство: строки удаляемых пользователей обезличиваются.
CREATE FUNCTION delete_workspace_data(ws bigint) RETURNS jsonb
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

-- Срок хранения текстов поисковых запросов — 60 дней от последнего появления в отчёте (ARCHITECTURE.md §2.4).
-- Удаляет пачку текстов, чьё последнее появление раньше cutoff (дату считает вызывающий в часовом поясе данных —
-- результат не зависит от часового пояса сервера). Агрегаты stat_rows остаются: у них нет FK на текст.
-- ПД вне workspace (152-ФЗ, ARCHITECTURE.md §2.5), срок — 30 дней: сессии — после окончания (истекла или отозвана);
-- email и логин Яндекса деактивированного пользователя — после деактивации обезличиваются. yandex_uid остаётся:
-- по нему деактивированный пользователь не войдёт снова под тем же аккаунтом. ip и user_agent его принятий
-- документов (legal_acceptances) обнуляются; сами принятия остаются. cutoff = now - 30 дней — из воркера.
-- Непустой проход — запись deletion_requests (system:retention). Повторный вызов безопасен.
CREATE FUNCTION purge_personal_data(cutoff timestamptz) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  s integer;
  u integer;
  i integer;
  a integer;
BEGIN
  DELETE FROM sessions WHERE least(expires_at, revoked_at) < cutoff;
  GET DIAGNOSTICS s = ROW_COUNT;
  UPDATE users SET email = '' WHERE status = 'deactivated' AND deactivated_at < cutoff AND email <> '';
  GET DIAGNOSTICS u = ROW_COUNT;
  UPDATE yandex_identities y SET login = '' FROM users
   WHERE users.id = y.user_id AND users.status = 'deactivated' AND users.deactivated_at < cutoff AND y.login <> '';
  GET DIAGNOSTICS i = ROW_COUNT;
  PERFORM set_config('app.anonymizing', 'on', true);
  UPDATE legal_acceptances l SET ip = NULL, user_agent = NULL FROM users
   WHERE users.id = l.user_id AND users.status = 'deactivated' AND users.deactivated_at < cutoff
     AND (l.ip IS NOT NULL OR l.user_agent IS NOT NULL);
  GET DIAGNOSTICS a = ROW_COUNT;
  PERFORM set_config('app.anonymizing', 'off', true);
  IF s + u + i + a > 0 THEN
    INSERT INTO deletion_requests (requested_by, scope, status, started_at, completed_at, verification, deleted_by)
    VALUES ('system:retention', 'personal_data_expired', 'completed', now(), now(),
            jsonb_build_object('sessions', s, 'users', u, 'yandex_identities', i, 'legal_acceptances', a,
                               'cutoff', cutoff),
            'purge_personal_data');
  END IF;
  RETURN s + u + i + a;
END $$;

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
  -- Блокировка текстов: новый показ (FK из синхронизации) ждёт удаления, а текст, который идущая синхронизация
  -- уже встретила снова, пропускаем (SKIP LOCKED) — не ждём её и не удаляем свежий показ.
  SELECT array_agg(id) INTO ids FROM (
    SELECT t.id FROM search_query_texts t
     WHERE t.id IN (SELECT query_id FROM search_query_sightings GROUP BY query_id HAVING max(seen_on) < cutoff)
     ORDER BY t.id LIMIT batch_size
     FOR UPDATE SKIP LOCKED) expired;
  -- Показ, закоммиченный до блокировки, виден только новому снимку: перепроверяем срок уже под блокировкой.
  SELECT array_agg(q) INTO ids FROM unnest(ids) q
   WHERE NOT EXISTS (SELECT 1 FROM search_query_sightings s WHERE s.query_id = q AND s.seen_on >= cutoff);
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

-- legal_acceptances: DELETE запрещён всем; UPDATE — только обезличивание внутри функций удаления и ретеншна
-- (delete_workspace_data, purge_personal_data: SECURITY DEFINER, метка транзакции app.anonymizing): ip и
-- user_agent → NULL, user_id → NULL или прежний; всё остальное — без изменений. Права UPDATE на таблицу нет
-- ни у одной рабочей роли — метку сама по себе выставить можно, но воспользоваться ею нечем.
CREATE FUNCTION legal_acceptance_anonymize_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND current_setting('app.anonymizing', true) = 'on'
     AND NEW.ip IS NULL AND NEW.user_agent IS NULL
     AND (NEW.user_id IS NULL OR NEW.user_id = OLD.user_id)
     AND (NEW.id, NEW.document, NEW.version, NEW.accepted_at, NEW.document_sha256, NEW.locale, NEW.workspace_id)
         IS NOT DISTINCT FROM
         (OLD.id, OLD.document, OLD.version, OLD.accepted_at, OLD.document_sha256, OLD.locale, OLD.workspace_id) THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'table legal_acceptances is append-only: % is not allowed (only anonymization)', TG_OP
    USING ERRCODE = 'insufficient_privilege';
END $$;
CREATE TRIGGER legal_acceptances_append_only BEFORE UPDATE OR DELETE ON legal_acceptances
  FOR EACH ROW EXECUTE FUNCTION legal_acceptance_anonymize_only();

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

