-- pg_restore clears the caller search_path while loading populated CHECK constraints.
ALTER FUNCTION value_is_valid_raw(jsonb) SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION value_is_valid(jsonb) SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION evidence_is_valid(jsonb) SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION values_are_valid(jsonb) SET search_path=pg_catalog,public,pg_temp;
