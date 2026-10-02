-- 0004: причина «недостаточно данных» в Value (unavailable_reason) — та же правка value_is_valid_raw, что в schema.sql.
-- Ключ необязателен: Value до 0004 записаны без него, а строки доказательной цепочки неизменяемы. Обязательность
-- держит модель (app/contract.py: Value); старые значения API читает с причиной no_data (Value.from_stored).
-- CHECK-ограничения ссылаются на value_is_valid (обёртку), её не трогаем; уже записанные строки новому правилу
-- удовлетворяют: ключа unavailable_reason в них нет.
CREATE OR REPLACE FUNCTION value_is_valid_raw(v jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT coalesce(
    jsonb_typeof(v) = 'object'
    AND v ?& array['amount', 'unit', 'source', 'period_from', 'period_to',
                   'calculation_type', 'data_status', 'data_sufficiency', 'snapshot_id']
    -- лишних ключей нет
    AND NOT EXISTS (SELECT 1 FROM jsonb_object_keys(v) AS k
                    WHERE k NOT IN ('amount', 'unit', 'source', 'period_from', 'period_to', 'calculation_type',
                                    'data_status', 'data_sufficiency', 'snapshot_id', 'rule_version', 'formula',
                                    'unavailable_reason'))
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
    -- причина «недостаточно данных»: только у unavailable и только из списка (contract.UNAVAILABLE_REASONS)
    AND jsonb_typeof(coalesce(v->'unavailable_reason', 'null'::jsonb)) IN ('null', 'string')
    AND (jsonb_typeof(coalesce(v->'unavailable_reason', 'null'::jsonb)) = 'null'
         OR (v->>'calculation_type' = 'unavailable'
             AND v->>'unavailable_reason' IN ('source_missing', 'no_conversions', 'history_insufficient',
                                              'volume_insufficient', 'no_forecast', 'no_data')))
    AND jsonb_typeof(v->'snapshot_id') = 'number' AND v->>'snapshot_id' ~ '^[0-9]+$'
    AND jsonb_typeof(v->'period_from') = 'string' AND jsonb_typeof(v->'period_to') = 'string'
    AND v->>'period_from' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' AND v->>'period_to' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    AND (v->>'period_from')::date <= (v->>'period_to')::date,
    false)
$$;
