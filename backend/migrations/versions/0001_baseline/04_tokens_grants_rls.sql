-- ============================================================================
-- OAuth-токены: приложение не видит шифротекст (column-level GRANT), работает через функции
-- ============================================================================
-- Писать и сбрасывать токен может приложение (OAuth-колбэк, отключение); читать — только роль воркера app_token.
-- Функции SECURITY DEFINER с фиксированным search_path, подключение ищется строго в пределах переданного workspace.
-- Аргумент ws сверяется с контекстом: если app.workspace_id выставлен (API в запросе, воркер в задаче) и не равен
-- ws — ошибка insufficient_privilege. Контекст не выставлен (системная роль, OAuth-колбэк до входа) — проверки
-- нет: workspace — явный параметр, право на него вызывающий проверяет сам (workspace_role).

-- Текущий workspace прикладной роли (app/tenancy.py); NULL — не выставлен. Основа политик RLS (конец файла).
CREATE FUNCTION app_workspace_id() RETURNS bigint
LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.workspace_id', true), '')::bigint $$;

CREATE FUNCTION require_workspace_context(ws bigint) RETURNS void
LANGUAGE plpgsql STABLE AS $$
BEGIN
  IF app_workspace_id() IS NOT NULL AND app_workspace_id() IS DISTINCT FROM ws THEN
    RAISE EXCEPTION 'workspace % is not the current workspace', ws USING ERRCODE = 'insufficient_privilege';
  END IF;
END $$;

CREATE FUNCTION set_connection_token(kind text, ws bigint, connection bigint, token bytea, expires timestamptz)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE n integer;
BEGIN
  PERFORM require_workspace_context(ws);
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
  PERFORM require_workspace_context(ws);
  IF new_status NOT IN ('disconnected', 'token_revoked') THEN
    RAISE EXCEPTION 'new_status must be disconnected or token_revoked';
  END IF;
  -- Ключ блокировки обновления пары (auth/tokens.py fresh_access_token): отключение ждёт идущий refresh,
  -- иначе тот записал бы новую пару и статус connected поверх отключения.
  PERFORM pg_advisory_xact_lock(hashtextextended('token:' || kind || ':' || connection, 0));
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
  PERFORM require_workspace_context(ws);
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

-- Workspace задачи воркера по её объекту — чтобы войти в workspace (app.workspace_id) до чтения самой задачи.
-- Раскрывает только номер workspace; NULL — объекта нет (удалён вместе с workspace) или вызывающий уже в контексте
-- другого workspace (чужой объект изнутри workspace не раскрывается).
CREATE FUNCTION task_workspace(kind text, obj bigint) RETURNS bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT w FROM (SELECT CASE kind
    WHEN 'sync_run' THEN (SELECT workspace_id FROM sync_runs WHERE id = task_workspace.obj)
    WHEN 'direct_account' THEN (SELECT c.workspace_id FROM direct_accounts a
                                JOIN direct_connections c ON c.id = a.direct_connection_id WHERE a.id = task_workspace.obj)
    WHEN 'measurement' THEN (SELECT i.workspace_id FROM measurements m JOIN issues i ON i.id = m.issue_id
                             WHERE m.id = task_workspace.obj)
  END AS w) t
  WHERE app_workspace_id() IS NULL OR app_workspace_id() = w
$$;

-- ============================================================================
-- Права
-- ============================================================================

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
-- В PostgreSQL ≤ 14 PUBLIC по умолчанию может создавать объекты в public — у приложения не должно быть DDL.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Приложение: читать всё, добавлять везде, изменять — только операционные таблицы. Без DELETE, без DDL.
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO app_rw;
GRANT UPDATE ON users, workspace_settings, telegram_links,
                direct_accounts, metrika_counters,
                sync_runs, snapshots, issues, notifications, outbox_events, subscriptions, payments,
                deletion_requests
             TO app_rw;
-- Сессии и привязки Telegram — служебные, не доказательные: выход из аккаунта удаляет строку.
GRANT DELETE ON sessions, telegram_links TO app_rw;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_rw;

-- Организации и команда (D3): только чтение; создание и изменение — функциями с проверкой actor (owner/admin).
-- Workspace: создаёт create_workspace; менять можно название и статус, но не организацию.
REVOKE INSERT ON organizations, organization_memberships, workspace_memberships, workspaces FROM app_rw;
GRANT UPDATE (name, status, deactivated_at) ON workspaces TO app_rw;
REVOKE EXECUTE ON FUNCTION require_org_manager(bigint, bigint), create_organization(bigint, text, text),
                           create_workspace(bigint, bigint, text),
                           set_organization_member(bigint, bigint, bigint, text),
                           remove_organization_member(bigint, bigint, bigint),
                           set_workspace_member(bigint, bigint, bigint, text),
                           remove_workspace_member(bigint, bigint, bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION create_organization(bigint, text, text), create_workspace(bigint, bigint, text),
                          set_organization_member(bigint, bigint, bigint, text),
                          remove_organization_member(bigint, bigint, bigint),
                          set_workspace_member(bigint, bigint, bigint, text),
                          remove_workspace_member(bigint, bigint, bigint) TO app_rw;

-- Принятия документов: ip и user_agent — ПД; приложение их пишет (INSERT), но не читает.
REVOKE SELECT ON legal_acceptances FROM app_rw;
GRANT SELECT (id, user_id, document, version, accepted_at, document_sha256, locale, workspace_id)
  ON legal_acceptances TO app_rw;

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
REVOKE EXECUTE ON FUNCTION purge_personal_data(timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION delete_workspace_data(bigint) TO app_deleter;
GRANT EXECUTE ON FUNCTION purge_search_query_texts(date, integer) TO app_deleter;
GRANT EXECUTE ON FUNCTION purge_personal_data(timestamptz) TO app_deleter;

-- Доступ к workspace и привязка задачи к workspace — до входа в него (app.workspace_id ещё не выставлен).
-- task_workspace изнутри чужого workspace отвечает NULL (см. функцию).
REVOKE EXECUTE ON FUNCTION workspace_role(bigint, bigint), user_workspaces(bigint),
                           task_workspace(text, bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION workspace_role(bigint, bigint), user_workspaces(bigint),
                          task_workspace(text, bigint) TO app_rw;

-- Таблицы из будущих миграций получают те же базовые права автоматически. Удаление их данных
-- delete_workspace_data само не узнает: новую таблицу с workspace нужно добавить в функцию и в test_lifecycle.
-- RLS тоже не включится сам: новой таблице с данными workspace нужна политика ниже (проверяет test_rls).
ALTER DEFAULT PRIVILEGES FOR ROLE app_migrator IN SCHEMA public GRANT SELECT, INSERT ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE app_migrator IN SCHEMA public GRANT USAGE ON SEQUENCES TO app_rw;

-- ============================================================================
-- Изоляция арендаторов: RLS — второй барьер после проверки доступа в коде (D13)
-- ============================================================================
-- Роли (создаются на уровне кластера, см. tests/conftest.py):
--   app_rw     — прикладная роль: API и воркеры задач одного workspace. Видит строки только того workspace,
--                что выставлен в app.workspace_id (API — SET LOCAL после workspace_role; воркер — на задачу,
--                app/tenancy.py). Не выставлен — 0 строк: запрос без фильтра не вернёт чужого клиента.
--                Организационного контекста нет: список workspace пользователя — user_workspaces(user), роль —
--                workspace_role(user, ws) (SECURITY DEFINER, представление effective_workspace_access).
--                Организации и команда — только чтение; создание организации и workspace, роли и исключение
--                участников — функции create_organization, create_workspace, set_/remove_organization_member,
--                set_/remove_workspace_member (проверяют, что actor — owner/admin организации).
--                workspaces: UPDATE только name, status, deactivated_at (organization_id неизменяем — триггер).
--                legal_acceptances: пишет всё, читает всё, кроме ip и user_agent (ПД).
--                Токены — set_connection_token / drop_connection_token (ws = app.workspace_id, если выставлен).
--   app_token  — член app_rw (+ connection_token): те же политики и права, что у app_rw.
--   app_system — член app_rw с отдельной разрешающей политикой «все строки»: системные задачи по многим
--                workspace (планировщик, захват и доставка outbox, уведомления, выбор замеров к запуску).
--                Те же права на таблицы, что у app_rw (в т.ч. без прямого изменения команды и без чтения
--                ip/user_agent) — только без фильтра по workspace.
--   app_deleter — никаких прав на таблицы: только delete_workspace_data, purge_personal_data,
--                purge_search_query_texts. Удаление пользователя обезличивает его legal_acceptances.
--   Функции SECURITY DEFINER (удаление, ретеншн, токены, проверка доступа, управление командой) работают от
--                владельца таблиц (app_migrator) и RLS не подчиняются; workspace / организация у них — явный
--                параметр, actor — пользователь сессии, которого передаёт API.
-- Без RLS: users, yandex_identities, sessions, telegram_links (данные пользователя, не workspace; приложение
-- фильтрует по пользователю сессии), organizations и organization_memberships (нужны до выбора workspace;
-- изменять — только функциями), releases и free_audit_claims (глобальные, без данных клиента).

-- app_workspace_id() — определена в разделе «OAuth-токены» (её используют и функции токенов).

DO $$
DECLARE
  t text;
  -- таблица → условие строки своего workspace
  rules jsonb := jsonb_build_object(
    'workspace_settings',   'workspace_id = app_workspace_id()',
    'direct_connections',   'workspace_id = app_workspace_id()',
    'metrika_connections',  'workspace_id = app_workspace_id()',
    'sync_runs',            'workspace_id = app_workspace_id()',
    'snapshots',            'workspace_id = app_workspace_id()',
    'search_query_texts',   'workspace_id = app_workspace_id()',
    'audit_runs',           'workspace_id = app_workspace_id()',
    'issues',               'workspace_id = app_workspace_id()',
    'outbox_events',        'workspace_id = app_workspace_id()',
    'digests',              'workspace_id = app_workspace_id()',
    'notifications',        'workspace_id = app_workspace_id()',
    'subscriptions',        'workspace_id = app_workspace_id()',
    'deletion_requests',    'workspace_id = app_workspace_id()',
    -- пользовательские документы (оферта, согласия) — без workspace; мандат агентства — только в своём
    'legal_acceptances',    'workspace_id IS NULL OR workspace_id = app_workspace_id()',
    -- список workspace пользователя — user_workspaces(), не прямой SELECT: вне контекста не видно ничего
    'workspaces',           'id = app_workspace_id()',
    'workspace_memberships', 'workspace_id = app_workspace_id()',
    -- без собственного workspace_id — через родителя (подзапрос по первичному ключу родителя)
    'direct_accounts',      'EXISTS (SELECT 1 FROM direct_connections p WHERE p.id = direct_accounts.direct_connection_id
                                     AND p.workspace_id = app_workspace_id())',
    'metrika_counters',     'EXISTS (SELECT 1 FROM metrika_connections p WHERE p.id = metrika_counters.metrika_connection_id
                                     AND p.workspace_id = app_workspace_id())',
    'stat_rows',            'EXISTS (SELECT 1 FROM snapshots p WHERE p.id = stat_rows.snapshot_id
                                     AND p.workspace_id = app_workspace_id())',
    'search_query_sightings', 'EXISTS (SELECT 1 FROM search_query_texts p WHERE p.id = search_query_sightings.query_id
                                       AND p.workspace_id = app_workspace_id())',
    'audit_run_snapshots',  'EXISTS (SELECT 1 FROM audit_runs p WHERE p.id = audit_run_snapshots.audit_run_id
                                     AND p.workspace_id = app_workspace_id())',
    'findings',             'EXISTS (SELECT 1 FROM issues p WHERE p.id = findings.issue_id AND p.workspace_id = app_workspace_id())',
    'recommendations',      'EXISTS (SELECT 1 FROM issues p WHERE p.id = recommendations.issue_id AND p.workspace_id = app_workspace_id())',
    'recommendation_events', 'EXISTS (SELECT 1 FROM issues p WHERE p.id = recommendation_events.issue_id AND p.workspace_id = app_workspace_id())',
    'recommendation_results', 'EXISTS (SELECT 1 FROM issues p WHERE p.id = recommendation_results.issue_id AND p.workspace_id = app_workspace_id())',
    'measurements',         'EXISTS (SELECT 1 FROM issues p WHERE p.id = measurements.issue_id AND p.workspace_id = app_workspace_id())',
    'explanations',         'EXISTS (SELECT 1 FROM findings f JOIN issues p ON p.id = f.issue_id WHERE f.id = explanations.finding_id
                                     AND p.workspace_id = app_workspace_id())',
    'subscription_events',  'EXISTS (SELECT 1 FROM subscriptions p WHERE p.id = subscription_events.subscription_id
                                     AND p.workspace_id = app_workspace_id())',
    -- платёж обезличенного (удалённого) workspace — только системе
    'payments',             'EXISTS (SELECT 1 FROM subscriptions p WHERE p.id = payments.subscription_id
                                     AND p.workspace_id = app_workspace_id())');
BEGIN
  FOR t IN SELECT jsonb_object_keys(rules) LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY tenant ON %I TO app_rw USING (%s)', t, rules->>t);
    EXECUTE format('CREATE POLICY system ON %I TO app_system USING (true) WITH CHECK (true)', t);
  END LOOP;
END $$;

