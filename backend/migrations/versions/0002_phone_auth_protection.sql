-- 0002: защита SMS-входа (коды, журнал попыток, лимиты) — та же правка, что раздел phone_auth в schema.sql.
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

