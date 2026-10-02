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

