-- 0006: high_cpa_measure@3 — окно «до» замера high_cpa = базовый период выполненного вывода (30 дней перед его неделей
-- оценки), а не 7 дней перед выполнением (app/audit/measurement.py, docs/ECONOMICS.md §5.1). Уже созданные замеры
-- не меняются: строки measurements неизменяемы, их методика (@2) остаётся в METHODS для воспроизводимости.
CREATE OR REPLACE FUNCTION create_measurement_on_done() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE d date := NEW.execution_date;
BEGIN
  INSERT INTO measurements (done_event_id, recommendation_id, issue_id, finding_id, policy,
                            before_from, before_to, after_from, after_to)
  SELECT NEW.id, NEW.recommendation_id, NEW.issue_id, NEW.finding_id,
         i.issue_type || CASE WHEN v3 THEN '_measure@3' ELSE '_measure@2' END,
         CASE WHEN v3 THEN (f.evidence->'cost'->>'period_from')::date - 30 ELSE d - 7 END,
         CASE WHEN v3 THEN (f.evidence->'cost'->>'period_from')::date - 1 ELSE d - 1 END,
         d + 1, d + 7
  FROM issues i JOIN findings f ON f.id = NEW.finding_id,
       -- @3 нужна неделя оценки вывода; без доказательства cost — прежняя @2, а не отказ в «Выполнено»
       LATERAL (SELECT i.issue_type = 'high_cpa' AND f.evidence ? 'cost' AS v3) x
  WHERE i.id = NEW.issue_id;
  RETURN NULL;
END
$$;
