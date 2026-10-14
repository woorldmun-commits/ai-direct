-- 0009: (1) база НДС целевого CPA. Расход в снимках — с НДС (реестр метрик, cost.vat = included); target_cpa
-- введён с НДС (true, как было до флага) или без него — тогда правила @3 сравнивают с ним target × (1 + НДС).
-- (2) high_cpa: новые замеры — по high_cpa_measure@3 («до» вне окна срабатывания правила, app/audit/measurement.py);
-- уже созданные замеры остаются на своей методике (@1/@2), остальные семейства — @2.
ALTER TABLE workspace_settings ADD COLUMN target_cpa_includes_vat boolean NOT NULL DEFAULT true;

CREATE OR REPLACE FUNCTION create_measurement_on_done() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE d date := NEW.execution_date;
BEGIN
  INSERT INTO measurements (done_event_id, recommendation_id, issue_id, finding_id, policy,
                            before_from, before_to, after_from, after_to)
  SELECT NEW.id, NEW.recommendation_id, NEW.issue_id, NEW.finding_id,
         i.issue_type || CASE WHEN i.issue_type = 'high_cpa' THEN '_measure@3' ELSE '_measure@2' END,
         d - 7, d - 1, d + 1, d + 7
  FROM issues i
  WHERE i.id = NEW.issue_id;
  RETURN NULL;
END
$$;
