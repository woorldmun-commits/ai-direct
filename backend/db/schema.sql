-- Схема MVP. Источник правды для первой миграции alembic.
-- Описание сущностей и состояний: docs/DATA_MODEL.md.
-- Выполняется ролью app_migrator (владелец всех объектов).
-- Роли app_rw, app_token (член app_rw), app_system (член app_rw), app_deleter, app_migrator создаются на уровне
-- кластера (Managed PostgreSQL / тестовый стенд): см. tests/conftest.py. Изоляция арендаторов (RLS) — в конце файла.

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

-- Принятие документов — доказательство на операторе (ч. 3 ст. 9 152-ФЗ). Каждый документ — отдельная строка:
-- согласие на обработку ПД оформляется отдельно от оферты (ч. 1 ст. 9, ред. 156-ФЗ с 01.09.2025). Append-only:
-- новая редакция или отзыв — новая строка, не правка старой.
-- document_sha256 — sha256 точного текста версии, который видел пользователь (реестр app/legal/documents.py);
-- locale — язык показанного текста; ip и user_agent — обстоятельства принятия, если известны.
-- agency_client_mandate — подтверждение агентства по клиенту (право передавать данные клиента, поручение клиента,
-- право давать доступ к Директу клиента): строка привязана к workspace клиента. workspace_id без FK, как у
-- deletion_requests: доказательство переживает удалённый workspace; существование и право — триггер при вставке.
-- Удаление пользователя (delete_workspace_data) строки не удаляет, а обезличивает: user_id, ip, user_agent → NULL;
-- документ, версия, document_sha256, locale и время остаются. ip и user_agent деактивированного пользователя
-- обнуляются через 30 дней (purge_personal_data), как email. Никакая другая правка не допускается (триггер
-- legal_acceptances_append_only). Срок хранения доказательств принятия — открытый вопрос юристу (LEGAL.md).
-- ip и user_agent — ПД: прикладная роль их пишет, но не читает (колоночные права, раздел «Права»).
CREATE TABLE legal_acceptances (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id         bigint REFERENCES users,  -- NULL — только у обезличенной строки (новая вставка: check_mandate)
  document        text NOT NULL CHECK (document IN ('offer', 'pd_consent', 'marketing', 'agency_client_mandate')),
  version         text NOT NULL CHECK (version ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}(\.[0-9]+)?$'),
  accepted_at     timestamptz NOT NULL,
  document_sha256 char(64) CHECK (document_sha256 ~ '^[0-9a-f]{64}$'),
  locale          text CHECK (locale ~ '^[a-z]{2}(-[A-Z]{2})?$'),
  ip              inet,
  user_agent      text CHECK (length(user_agent) <= 256),
  workspace_id    bigint,
  -- мандат — всегда по конкретному клиенту (workspace); остальные документы — пользовательские, без workspace
  CHECK ((document = 'agency_client_mandate') = (workspace_id IS NOT NULL)),
  -- обезличенная строка не хранит обстоятельств принятия
  CHECK (user_id IS NOT NULL OR (ip IS NULL AND user_agent IS NULL))
);
-- Хэш текста и язык обязательны для новых записей. NOT VALID: строки, принятые до появления реестра текстов
-- (при миграции существующей БД), задним числом не проверяются; любая новая вставка — проверяется.
ALTER TABLE legal_acceptances ADD CONSTRAINT legal_acceptances_text_evidence
  CHECK (document_sha256 IS NOT NULL AND locale IS NOT NULL) NOT VALID;
CREATE INDEX legal_acceptances_user ON legal_acceptances (user_id, document);
CREATE INDEX legal_acceptances_workspace ON legal_acceptances (workspace_id) WHERE workspace_id IS NOT NULL;

-- ============================================================================
-- Организации и доступ (D3): роль в организации + роль в workspace
-- ============================================================================
-- owner/admin организации видят и ведут все её workspace; member — только те, где у него есть
-- workspace_memberships. Эффективная роль считается в одном месте — effective_workspace_access / workspace_role.

CREATE TABLE organizations (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name       text NOT NULL,
  kind       text NOT NULL CHECK (kind IN ('business', 'agency')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE organization_memberships (
  user_id         bigint NOT NULL REFERENCES users,
  organization_id bigint NOT NULL REFERENCES organizations,
  org_role        text NOT NULL CHECK (org_role IN ('owner', 'admin', 'member')),
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, organization_id)
);
CREATE INDEX organization_memberships_org ON organization_memberships (organization_id);

CREATE TABLE workspaces (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  organization_id bigint NOT NULL REFERENCES organizations,
  name            text NOT NULL,
  status          text NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active', 'deactivated', 'deletion_pending')),
  created_at      timestamptz NOT NULL DEFAULT now(),
  deactivated_at  timestamptz,
  CHECK ((status = 'active') = (deactivated_at IS NULL)),
  UNIQUE (id, organization_id)  -- цель составного FK workspace_memberships
);
CREATE INDEX workspaces_organization ON workspaces (organization_id);

-- Workspace не переезжает в другую организацию: иначе вместе с данными клиента уехал бы и доступ к ним
-- (owner/admin другой организации). Прикладной роли UPDATE organization_id и не выдан (раздел «Права»).
CREATE FUNCTION workspace_organization_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
    RAISE EXCEPTION 'workspaces.organization_id is immutable' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER workspaces_organization_immutable BEFORE UPDATE OF organization_id ON workspaces
  FOR EACH ROW EXECUTE FUNCTION workspace_organization_immutable();

-- Участник workspace — обязательно участник организации этого workspace: составные FK, а не проверка кодом
-- (без гонки «удалили из организации, пока добавляли в workspace»). organization_id заполняет триггер из
-- workspaces — приложение передаёт только user, workspace и роль. Удаление участника из организации каскадно
-- удаляет его workspace_memberships (ON DELETE CASCADE).
CREATE TABLE workspace_memberships (
  user_id         bigint NOT NULL,
  workspace_id    bigint NOT NULL,
  organization_id bigint NOT NULL,
  ws_role         text NOT NULL CHECK (ws_role IN ('approver', 'analyst', 'viewer')),
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, workspace_id),
  FOREIGN KEY (workspace_id, organization_id) REFERENCES workspaces (id, organization_id),
  FOREIGN KEY (user_id, organization_id) REFERENCES organization_memberships (user_id, organization_id)
    ON DELETE CASCADE
);
CREATE INDEX workspace_memberships_workspace ON workspace_memberships (workspace_id);
CREATE INDEX workspace_memberships_org_user ON workspace_memberships (user_id, organization_id);

CREATE FUNCTION fill_membership_organization() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.organization_id := (SELECT organization_id FROM workspaces WHERE id = NEW.workspace_id);
  RETURN NEW;
END
$$;
CREATE TRIGGER workspace_memberships_organization BEFORE INSERT OR UPDATE ON workspace_memberships
  FOR EACH ROW EXECUTE FUNCTION fill_membership_organization();

-- Хотя бы один owner у организации. Проверка отложена до COMMIT: передача владения (добавить нового owner,
-- понизить старого) — в любом порядке внутри транзакции; организация и её owner создаются одной транзакцией.
-- Проверки сериализуются по строке организации: перед проверкой — пустой UPDATE этой строки (не SELECT FOR UPDATE).
-- Два параллельных понижения двух владельцев: в READ COMMITTED вторая проверка ждёт первую и видит её результат;
-- в REPEATABLE READ / SERIALIZABLE снимок второй транзакции старый, и только новая версия строки (а не блокировка)
-- даёт ей serialization_failure вместо COMMIT организации без owner.
-- SECURITY DEFINER: проверка видит всех участников независимо от RLS вызывающего. Удалённую организацию
-- (delete_workspace_data) не проверяем.
-- Открытый вопрос: деактивация единственного owner (users.status = 'deactivated') этим триггером не ловится —
-- организация остаётся с owner без доступа; решение (запрет, передача владения) — за продуктом.
CREATE FUNCTION check_organization_has_owner() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE org bigint;
BEGIN
  IF TG_TABLE_NAME = 'organizations' THEN
    org := NEW.id;
  ELSE
    org := OLD.organization_id;
  END IF;
  UPDATE organizations SET name = name WHERE id = org;
  IF FOUND AND NOT EXISTS (SELECT 1 FROM organization_memberships
                           WHERE organization_id = org AND org_role = 'owner') THEN
    RAISE EXCEPTION 'organization % must have at least one owner', org
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NULL;
END
$$;
CREATE CONSTRAINT TRIGGER organizations_has_owner AFTER INSERT ON organizations
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_organization_has_owner();
CREATE CONSTRAINT TRIGGER organization_memberships_has_owner AFTER UPDATE OR DELETE ON organization_memberships
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_organization_has_owner();

-- Эффективный доступ пользователя к workspace — единственная точка проверки. role: owner · admin (всё в любом
-- workspace организации) · approver · analyst · viewer (только свой workspace). Нет строки — нет доступа (API: 404,
-- не 403). Деактивированный пользователь доступа не имеет. security_invoker: прикладная роль видит через
-- представление только то, что ей разрешает RLS.
CREATE VIEW effective_workspace_access WITH (security_invoker = true) AS
SELECT om.user_id, w.id AS workspace_id, w.organization_id, om.org_role, wm.ws_role,
       CASE WHEN om.org_role IN ('owner', 'admin') THEN om.org_role ELSE wm.ws_role END AS role
FROM organization_memberships om
JOIN users u ON u.id = om.user_id AND u.status = 'active'
JOIN workspaces w ON w.organization_id = om.organization_id
LEFT JOIN workspace_memberships wm ON wm.user_id = om.user_id AND wm.workspace_id = w.id
WHERE om.org_role IN ('owner', 'admin') OR wm.ws_role IS NOT NULL;

-- Проверка выполняется до входа в workspace (app.workspace_id ещё не выставлен), поэтому SECURITY DEFINER:
-- отвечает только на вопрос «какая роль у пользователя в этом workspace» и ничего больше не раскрывает.
CREATE FUNCTION workspace_role(usr bigint, ws bigint) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT role FROM effective_workspace_access WHERE user_id = usr AND workspace_id = ws
$$;

-- Workspace пользователя (переключатель в UI) — из того же представления.
CREATE FUNCTION user_workspaces(usr bigint) RETURNS TABLE (workspace_id bigint, organization_id bigint, role text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT a.workspace_id, a.organization_id, a.role FROM effective_workspace_access a WHERE a.user_id = usr
  ORDER BY a.workspace_id
$$;

-- Управление организацией и командой — только этими функциями. У app_rw нет INSERT/UPDATE/DELETE на
-- organizations, organization_memberships, workspace_memberships и INSERT на workspaces (раздел «Права»).
-- actor — пользователь сессии, его передаёт API после аутентификации (так же, как usr в workspace_role).
-- Функция проверяет, что actor — активный owner/admin организации; назначить owner, изменить или исключить
-- owner может только owner. Нет права — insufficient_privilege. Хотя бы один owner — триггер выше.
CREATE FUNCTION require_org_manager(actor bigint, org bigint) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE r text;
BEGIN
  SELECT m.org_role INTO r FROM organization_memberships m JOIN users u ON u.id = m.user_id AND u.status = 'active'
   WHERE m.user_id = actor AND m.organization_id = org AND m.org_role IN ('owner', 'admin');
  IF r IS NULL THEN
    RAISE EXCEPTION 'user % cannot manage organization %', actor, org USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN r;
END $$;

-- Новая организация: actor становится её owner (одна транзакция — триггер owner доволен).
CREATE FUNCTION create_organization(actor bigint, org_name text, org_kind text) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE org bigint;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM users WHERE id = actor AND status = 'active') THEN
    RAISE EXCEPTION 'user % is not active', actor USING ERRCODE = 'insufficient_privilege';
  END IF;
  INSERT INTO organizations (name, kind) VALUES (org_name, org_kind) RETURNING id INTO org;
  INSERT INTO organization_memberships (user_id, organization_id, org_role) VALUES (actor, org, 'owner');
  RETURN org;
END $$;

CREATE FUNCTION create_workspace(actor bigint, org bigint, ws_name text) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE ws bigint;
BEGIN
  PERFORM require_org_manager(actor, org);
  INSERT INTO workspaces (organization_id, name) VALUES (org, ws_name) RETURNING id INTO ws;
  RETURN ws;
END $$;

-- Добавить участника организации или сменить его роль.
CREATE FUNCTION set_organization_member(actor bigint, org bigint, usr bigint, new_role text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF require_org_manager(actor, org) <> 'owner' AND (new_role = 'owner' OR EXISTS (
       SELECT 1 FROM organization_memberships WHERE user_id = usr AND organization_id = org AND org_role = 'owner')) THEN
    RAISE EXCEPTION 'only an owner can grant or change the owner role' USING ERRCODE = 'insufficient_privilege';
  END IF;
  INSERT INTO organization_memberships (user_id, organization_id, org_role) VALUES (usr, org, new_role)
  ON CONFLICT (user_id, organization_id) DO UPDATE SET org_role = EXCLUDED.org_role;
END $$;

-- Исключить из организации; его workspace_memberships удаляются каскадом.
CREATE FUNCTION remove_organization_member(actor bigint, org bigint, usr bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF require_org_manager(actor, org) <> 'owner' AND EXISTS (
       SELECT 1 FROM organization_memberships WHERE user_id = usr AND organization_id = org AND org_role = 'owner') THEN
    RAISE EXCEPTION 'only an owner can remove an owner' USING ERRCODE = 'insufficient_privilege';
  END IF;
  DELETE FROM organization_memberships WHERE user_id = usr AND organization_id = org;
END $$;

-- Роль участника организации в workspace (добавить или сменить). Не участник организации — FK.
CREATE FUNCTION set_workspace_member(actor bigint, ws bigint, usr bigint, new_role text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  PERFORM require_org_manager(actor, (SELECT organization_id FROM workspaces WHERE id = ws));
  INSERT INTO workspace_memberships (user_id, workspace_id, ws_role) VALUES (usr, ws, new_role)
  ON CONFLICT (user_id, workspace_id) DO UPDATE SET ws_role = EXCLUDED.ws_role;
END $$;

CREATE FUNCTION remove_workspace_member(actor bigint, ws bigint, usr bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  PERFORM require_org_manager(actor, (SELECT organization_id FROM workspaces WHERE id = ws));
  DELETE FROM workspace_memberships WHERE user_id = usr AND workspace_id = ws;
END $$;

-- Мандат агентства: workspace существует, принадлежит агентству, и подтверждает его owner/admin организации.
CREATE FUNCTION check_mandate() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF NEW.user_id IS NULL THEN  -- NULL допустим только после обезличивания, не при вставке
    RAISE EXCEPTION 'legal_acceptances: user_id is required' USING ERRCODE = 'not_null_violation';
  END IF;
  -- без workspace строку отклонит CHECK таблицы
  IF NEW.document = 'agency_client_mandate' AND NEW.workspace_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM effective_workspace_access a JOIN organizations o ON o.id = a.organization_id
       WHERE a.user_id = NEW.user_id AND a.workspace_id = NEW.workspace_id
         AND a.role IN ('owner', 'admin') AND o.kind = 'agency') THEN
    RAISE EXCEPTION 'agency_client_mandate: workspace % is not an agency client managed by user %',
      NEW.workspace_id, NEW.user_id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END
$$;
CREATE TRIGGER legal_acceptances_mandate BEFORE INSERT ON legal_acceptances
  FOR EACH ROW EXECUTE FUNCTION check_mandate();

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
-- is_selected = «включён в анализ» (D4): выбранных кабинетов может быть несколько. Синхронизация, снимок и аудит —
-- по каждому выбранному кабинету отдельно. Сколько кабинетов можно включить — лимит тарифа (max_ad_accounts),
-- проверяется кодом, а не схемой.

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

-- ============================================================================
-- Вход по номеру телефона: коды и журнал попыток (D2; HOLD до юриста — модуль за флагом PHONE_AUTH_ENABLED)
-- ============================================================================
-- Не данные workspace — без RLS (как users и sessions). Номер, IP и device id — ПД: в БД только HMAC-SHA256 с ключом
-- вне БД (PHONE_AUTH_HMAC_KEY); код — только HMAC (номер + код). Открытого номера, IP и кода здесь нет.
-- У рабочих ролей нет прав на таблицы: выдача, проверка, журнал и счётчики — только функциями SECURITY DEFINER
-- (app/auth/phone.py). Так лимиты нельзя обойти прямым INSERT кода, счётчики — подправить UPDATE/DELETE, а хэши
-- номеров и IP — прочитать массово. Удаление — только purge_phone_auth (роль app_deleter).

-- Одноразовый код: TTL задаёт выдача (5 мин), до 5 неверных попыток, одноразовый (used_at), новый код гасит
-- предыдущий (superseded_at). Живой код на номер — не больше одного (уникальный частичный индекс).
CREATE TABLE phone_auth_codes (  -- [O]
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  phone_hash    bytea NOT NULL CHECK (length(phone_hash) = 32),
  code_hash     bytea NOT NULL CHECK (length(code_hash) = 32),
  created_at    timestamptz NOT NULL,
  expires_at    timestamptz NOT NULL,
  attempts      smallint NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 5),
  used_at       timestamptz,
  superseded_at timestamptz,
  CHECK (expires_at > created_at),
  CHECK (used_at IS NULL OR superseded_at IS NULL)
);
CREATE UNIQUE INDEX phone_auth_codes_one_live ON phone_auth_codes (phone_hash)
  WHERE used_at IS NULL AND superseded_at IS NULL;
CREATE INDEX phone_auth_codes_expires ON phone_auth_codes (expires_at);

-- Журнал попыток (append-only; удаляет только purge_phone_auth под меткой app.deleting). Он же — источник счётчиков
-- лимитов (code_issued) и алертов. phone_prefix — «+79XX» (код оператора/региона, не номер).
CREATE TABLE phone_auth_events (  -- [A]
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at  timestamptz NOT NULL,
  event        text NOT NULL CHECK (event IN ('code_issued', 'sms_sent', 'sms_failed', 'rate_limited',
                                              'global_cap_reached', 'captcha_required', 'number_rejected',
                                              'code_invalid', 'code_verified')),
  reason       text CHECK (reason IN ('cooldown', 'phone_hour', 'phone_day', 'ip_hour', 'global_day')),
  phone_hash   bytea CHECK (length(phone_hash) = 32),
  ip_hash      bytea CHECK (length(ip_hash) = 32),
  device_hash  bytea CHECK (length(device_hash) = 32),
  phone_prefix text CHECK (phone_prefix ~ '^\+79[0-9]{2}$')
);
CREATE INDEX phone_auth_events_time ON phone_auth_events (occurred_at);
CREATE INDEX phone_auth_events_phone ON phone_auth_events (phone_hash, occurred_at) WHERE event = 'code_issued';
CREATE INDEX phone_auth_events_ip ON phone_auth_events (ip_hash, occurred_at) WHERE event = 'code_issued';
CREATE INDEX phone_auth_events_device ON phone_auth_events (device_hash, occurred_at) WHERE event = 'code_issued';
CREATE TRIGGER phone_auth_events_append_only BEFORE UPDATE OR DELETE ON phone_auth_events
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- Сколько ждать до места в скользящем окне (0 — место есть): выйти из окна должна (cnt - lim + 1)-я по старшинству
-- выдача. kind: phone · ip · global. Вызывается только из phone_code_request (под её блокировкой).
CREATE FUNCTION phone_auth_retry_after(kind text, hash bytea, win interval, lim integer, at timestamptz)
RETURNS integer
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
DECLARE
  cnt integer;
  pivot timestamptz;
BEGIN
  SELECT count(*) INTO cnt FROM phone_auth_events e
   WHERE e.event = 'code_issued' AND e.occurred_at > at - win AND e.occurred_at <= at
     AND CASE kind WHEN 'phone' THEN e.phone_hash = hash WHEN 'ip' THEN e.ip_hash = hash ELSE true END;
  IF cnt < lim THEN
    RETURN 0;
  END IF;
  SELECT e.occurred_at INTO pivot FROM phone_auth_events e
   WHERE e.event = 'code_issued' AND e.occurred_at > at - win AND e.occurred_at <= at
     AND CASE kind WHEN 'phone' THEN e.phone_hash = hash WHEN 'ip' THEN e.ip_hash = hash ELSE true END
   ORDER BY e.occurred_at OFFSET cnt - lim LIMIT 1;
  RETURN greatest(1, ceil(extract(epoch FROM pivot + win - at))::integer);
END $$;

-- Выдача кода: все лимиты проверяются и код пишется под одной транзакционной блокировкой — параллельные запросы
-- (в т.ч. с разных номеров одного IP и глобальный потолок) сериализуются и лимит не превышают. Только
-- READ COMMITTED: каждый запрос функции после блокировки видит уже закоммиченные выдачи. Результат:
-- issued · rate_limited | global_cap_reached (+ retry_after, с) · captcha_required. Глобальный потолок — ещё и
-- событие global_cap_reached в журнале (алерт).
CREATE FUNCTION phone_code_request(p_phone_hash bytea, p_ip_hash bytea, p_device_hash bytea, p_prefix text,
                                   p_code_hash bytea, p_captcha_ok boolean, p_now timestamptz,
                                   p_ttl_s integer, p_cooldown_s integer, p_phone_hour integer, p_phone_day integer,
                                   p_ip_hour integer, p_global_day integer, p_captcha_ip integer,
                                   p_captcha_device integer)
RETURNS TABLE (status text, retry_after integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  last_issued timestamptz;
  r_cooldown integer := 0;
  r_phone_hour integer;
  r_phone_day integer;
  r_ip_hour integer;
  r_global integer;
  wait integer;
  ip_recent integer;
  device_recent integer := 0;
BEGIN
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'phone_code_request requires READ COMMITTED';
  END IF;
  IF p_phone_hash IS NULL OR p_ip_hash IS NULL OR p_code_hash IS NULL OR p_now IS NULL THEN
    RAISE EXCEPTION 'phone, ip, code and time are required';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtext('phone_auth'), 1);
  SELECT max(occurred_at) INTO last_issued FROM phone_auth_events
   WHERE event = 'code_issued' AND phone_hash = p_phone_hash AND occurred_at <= p_now;
  IF last_issued > p_now - make_interval(secs => p_cooldown_s) THEN
    r_cooldown := greatest(1, ceil(extract(epoch FROM last_issued + make_interval(secs => p_cooldown_s) - p_now))::integer);
  END IF;
  r_phone_hour := phone_auth_retry_after('phone', p_phone_hash, interval '1 hour', p_phone_hour, p_now);
  r_phone_day := phone_auth_retry_after('phone', p_phone_hash, interval '1 day', p_phone_day, p_now);
  r_ip_hour := phone_auth_retry_after('ip', p_ip_hash, interval '1 hour', p_ip_hour, p_now);
  r_global := phone_auth_retry_after('global', NULL, interval '1 day', p_global_day, p_now);
  wait := greatest(r_cooldown, r_phone_hour, r_phone_day, r_ip_hour, r_global);
  IF wait > 0 THEN
    INSERT INTO phone_auth_events (occurred_at, event, reason, phone_hash, ip_hash, device_hash, phone_prefix)
    VALUES (p_now, CASE WHEN r_global > 0 THEN 'global_cap_reached' ELSE 'rate_limited' END,
            CASE WHEN r_global > 0 THEN 'global_day' WHEN wait = r_phone_day THEN 'phone_day'
                 WHEN wait = r_phone_hour THEN 'phone_hour' WHEN wait = r_ip_hour THEN 'ip_hour' ELSE 'cooldown' END,
            p_phone_hash, p_ip_hash, p_device_hash, p_prefix);
    RETURN QUERY SELECT CASE WHEN r_global > 0 THEN 'global_cap_reached' ELSE 'rate_limited' END, wait;
    RETURN;
  END IF;
  SELECT count(*) INTO ip_recent FROM phone_auth_events
   WHERE event = 'code_issued' AND ip_hash = p_ip_hash AND occurred_at > p_now - interval '1 hour'
     AND occurred_at <= p_now;
  IF p_device_hash IS NOT NULL THEN
    SELECT count(*) INTO device_recent FROM phone_auth_events
     WHERE event = 'code_issued' AND device_hash = p_device_hash AND occurred_at > p_now - interval '1 hour'
       AND occurred_at <= p_now;
  END IF;
  IF NOT coalesce(p_captcha_ok, false) AND (ip_recent >= p_captcha_ip OR device_recent >= p_captcha_device) THEN
    INSERT INTO phone_auth_events (occurred_at, event, phone_hash, ip_hash, device_hash, phone_prefix)
    VALUES (p_now, 'captcha_required', p_phone_hash, p_ip_hash, p_device_hash, p_prefix);
    RETURN QUERY SELECT 'captcha_required'::text, 0;
    RETURN;
  END IF;
  UPDATE phone_auth_codes SET superseded_at = p_now
   WHERE phone_hash = p_phone_hash AND used_at IS NULL AND superseded_at IS NULL;
  INSERT INTO phone_auth_codes (phone_hash, code_hash, created_at, expires_at)
  VALUES (p_phone_hash, p_code_hash, p_now, p_now + make_interval(secs => p_ttl_s));
  INSERT INTO phone_auth_events (occurred_at, event, phone_hash, ip_hash, device_hash, phone_prefix)
  VALUES (p_now, 'code_issued', p_phone_hash, p_ip_hash, p_device_hash, p_prefix);
  RETURN QUERY SELECT 'issued'::text, 0;
END $$;

-- Живой код номера для проверки; строка заблокирована до конца транзакции вызывающего. Хэши сравнивает приложение
-- за постоянное время (hmac.compare_digest), итог пишет phone_code_record в той же транзакции.
CREATE FUNCTION phone_code_for_check(p_phone_hash bytea, p_now timestamptz)
RETURNS TABLE (code_id bigint, code_hash bytea)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  RETURN QUERY SELECT c.id, c.code_hash FROM phone_auth_codes c
   WHERE c.phone_hash = p_phone_hash AND c.used_at IS NULL AND c.superseded_at IS NULL
     AND c.attempts < 5 AND c.expires_at > p_now
   FOR UPDATE;
END $$;

-- Итог проверки. Верный код и p_consume — код гасится (вход состоялся); без p_consume код остаётся живым (нужно
-- принять оферту: API_CONTRACT §11, 422 acceptance_required). Неверный — +1 попытка (пятая гасит код), code_invalid.
CREATE FUNCTION phone_code_record(p_code_id bigint, p_phone_hash bytea, p_ok boolean, p_consume boolean,
                                  p_ip_hash bytea, p_prefix text, p_now timestamptz) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  live boolean := false;
BEGIN
  SELECT true INTO live FROM phone_auth_codes
   WHERE id = p_code_id AND phone_hash = p_phone_hash AND used_at IS NULL AND superseded_at IS NULL
     AND attempts < 5 AND expires_at > p_now
   FOR UPDATE;
  live := coalesce(live, false);
  IF live AND p_ok THEN
    IF p_consume THEN
      UPDATE phone_auth_codes SET used_at = p_now WHERE id = p_code_id;
      INSERT INTO phone_auth_events (occurred_at, event, phone_hash, ip_hash, phone_prefix)
      VALUES (p_now, 'code_verified', p_phone_hash, p_ip_hash, p_prefix);
    END IF;
    RETURN true;
  END IF;
  IF live THEN
    UPDATE phone_auth_codes SET attempts = attempts + 1 WHERE id = p_code_id;
  END IF;
  INSERT INTO phone_auth_events (occurred_at, event, phone_hash, ip_hash, phone_prefix)
  VALUES (p_now, 'code_invalid', p_phone_hash, p_ip_hash, p_prefix);
  RETURN false;
END $$;

-- События вне выдачи и проверки: результат отправки у провайдера (после COMMIT выдачи) и отказ по номеру.
CREATE FUNCTION phone_auth_log(p_event text, p_phone_hash bytea, p_ip_hash bytea, p_device_hash bytea,
                               p_prefix text, p_now timestamptz) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF p_event IS NULL OR p_event NOT IN ('sms_sent', 'sms_failed', 'number_rejected') THEN
    RAISE EXCEPTION 'event % is written only by issuance and verification', p_event
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  INSERT INTO phone_auth_events (occurred_at, event, phone_hash, ip_hash, device_hash, phone_prefix)
  VALUES (p_now, p_event, p_phone_hash, p_ip_hash, p_device_hash, p_prefix);
END $$;

-- Счётчики за последний час для алертов (SMS pumping, перебор кодов): событие × префикс «+79XX».
CREATE FUNCTION phone_auth_last_hour(p_now timestamptz)
RETURNS TABLE (event text, phone_prefix text, n bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT e.event, e.phone_prefix, count(*) FROM phone_auth_events e
   WHERE e.occurred_at > p_now - interval '1 hour' AND e.occurred_at <= p_now
   GROUP BY e.event, e.phone_prefix
$$;

-- Ретеншн 30 дней (ARCHITECTURE.md §2.5, как purge_personal_data): события до cutoff и коды, истёкшие до cutoff.
-- cutoff = now - 30 дней — из воркера. Непустой проход — запись deletion_requests (system:retention).
CREATE FUNCTION purge_phone_auth(cutoff timestamptz) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  e integer;
  c integer;
BEGIN
  PERFORM set_config('app.deleting', 'on', true);
  DELETE FROM phone_auth_events WHERE occurred_at < cutoff;
  GET DIAGNOSTICS e = ROW_COUNT;
  PERFORM set_config('app.deleting', 'off', true);
  DELETE FROM phone_auth_codes WHERE expires_at < cutoff;
  GET DIAGNOSTICS c = ROW_COUNT;
  IF e + c > 0 THEN
    INSERT INTO deletion_requests (requested_by, scope, status, started_at, completed_at, verification, deleted_by)
    VALUES ('system:retention', 'personal_data_expired', 'completed', now(), now(),
            jsonb_build_object('phone_auth_events', e, 'phone_auth_codes', c, 'cutoff', cutoff), 'purge_phone_auth');
  END IF;
  RETURN e + c;
END $$;

-- Права: таблицы рабочим ролям недоступны вовсе (в т.ч. базовые SELECT/INSERT из ALTER DEFAULT PRIVILEGES).
REVOKE ALL ON phone_auth_codes, phone_auth_events FROM PUBLIC, app_rw;
REVOKE EXECUTE ON FUNCTION
  phone_auth_retry_after(text, bytea, interval, integer, timestamptz),
  phone_code_request(bytea, bytea, bytea, text, bytea, boolean, timestamptz, integer, integer, integer, integer,
                     integer, integer, integer, integer),
  phone_code_for_check(bytea, timestamptz),
  phone_code_record(bigint, bytea, boolean, boolean, bytea, text, timestamptz),
  phone_auth_log(text, bytea, bytea, bytea, text, timestamptz),
  phone_auth_last_hour(timestamptz),
  purge_phone_auth(timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
  phone_code_request(bytea, bytea, bytea, text, bytea, boolean, timestamptz, integer, integer, integer, integer,
                     integer, integer, integer, integer),
  phone_code_for_check(bytea, timestamptz),
  phone_code_record(bigint, bytea, boolean, boolean, bytea, text, timestamptz),
  phone_auth_log(text, bytea, bytea, bytea, text, timestamptz),
  phone_auth_last_hour(timestamptz) TO app_rw;
GRANT EXECUTE ON FUNCTION purge_phone_auth(timestamptz) TO app_deleter;

