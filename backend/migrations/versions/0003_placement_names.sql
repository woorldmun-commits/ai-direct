-- 0003: справочник имён площадок РСЯ — та же правка, что раздел placement_names в schema.sql.
-- ============================================================================
-- Справочник имён площадок РСЯ (zero_conv_placements): stat_rows.object_id уровня placement → имя
-- ============================================================================
-- Глобальный, а не данные workspace — без RLS (как releases). Имя — нормализованный домен сайта или идентификатор
-- приложения (app/sync/sanitize.py: sanitize_placement), не ПД и не текст пользователя; id — хэш имени
-- (app/sync/parse.py: placement_id), одинаковый во всех workspace, поэтому строка не говорит, чей это кабинет и
-- кто на площадке тратил. Маска «***» сюда не пишется: CHECK повторяет allowlist формы из sanitize_placement.
-- Append-only: id — хэш имени, имя по id не меняется. Приложение добавляет (INSERT … ON CONFLICT DO NOTHING) и
-- читает; UPDATE и DELETE нет ни у одной рабочей роли (и триггер запрещает их всем).
CREATE TABLE placement_names (  -- [A]
  id   bigint PRIMARY KEY CHECK (id >= 0),
  name text NOT NULL CHECK (length(name) <= 253
                            AND name ~ '^[0-9a-zа-яё_-]{1,63}(\.[0-9a-zа-яё_-]{1,63})*$'
                            AND name ~ '[a-zа-яё]')
);
CREATE TRIGGER placement_names_append_only BEFORE UPDATE OR DELETE ON placement_names
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
REVOKE ALL ON placement_names FROM PUBLIC;
GRANT SELECT, INSERT ON placement_names TO app_rw;
