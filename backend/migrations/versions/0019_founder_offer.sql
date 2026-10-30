-- Separate test/live capacity. Completed enrolments cannot be reset by deleting a workspace.
CREATE TABLE founder_enrollments (
  user_id bigint REFERENCES users ON DELETE SET NULL,
  test boolean NOT NULL,
  slot smallint NOT NULL CHECK(slot BETWEEN 1 AND 20),
  workspace_id bigint REFERENCES workspaces ON DELETE SET NULL,
  payments smallint NOT NULL DEFAULT 0 CHECK(payments BETWEEN 0 AND 3),
  PRIMARY KEY(test,slot), UNIQUE(user_id,test)
);
REVOKE ALL ON founder_enrollments FROM PUBLIC,app_rw,app_token,app_system,app_deleter;

CREATE FUNCTION founder_offer(actor bigint,ws bigint,is_test boolean,reserve_slot boolean DEFAULT false)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE used integer; bound bigint; free_slot smallint;
BEGIN
  PERFORM billing_workspace(ws);
  IF coalesce(workspace_role(actor,ws),'') NOT IN ('owner','admin') THEN
    RAISE EXCEPTION 'billing manager required' USING ERRCODE='insufficient_privilege';
  END IF;
  IF reserve_slot THEN PERFORM pg_advisory_xact_lock(hashtextextended('inrou-founder:'||is_test::text,0)); END IF;
  SELECT payments,workspace_id INTO used,bound FROM founder_enrollments WHERE user_id=actor AND test=is_test;
  IF FOUND THEN RETURN CASE WHEN bound=ws THEN 3-used ELSE 0 END; END IF;
  IF EXISTS(SELECT 1 FROM billing_orders WHERE actor_id=actor AND test=is_test AND status='succeeded') THEN RETURN 0; END IF;
  SELECT n::smallint INTO free_slot FROM generate_series(1,20) n WHERE NOT EXISTS
    (SELECT 1 FROM founder_enrollments f WHERE f.test=is_test AND f.slot=n) ORDER BY n LIMIT 1;
  IF free_slot IS NULL THEN RETURN 0; END IF;
  IF reserve_slot THEN
    INSERT INTO founder_enrollments(user_id,test,slot,workspace_id) VALUES(actor,is_test,free_slot,ws);
  END IF;
  RETURN 3;
END $$;
REVOKE ALL ON FUNCTION founder_offer(bigint,bigint,boolean,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION founder_offer(bigint,bigint,boolean,boolean) TO app_rw;

CREATE FUNCTION founder_payment() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
  IF NEW.status='succeeded' AND OLD.status<>'succeeded' AND NEW.sku='control' AND NEW.amount_minor=199000 THEN
    UPDATE founder_enrollments SET payments=least(payments+1,3)
    WHERE user_id=NEW.actor_id AND test=NEW.test AND workspace_id=NEW.workspace_id;
  ELSIF NEW.status='canceled' AND OLD.status<>'canceled' THEN
    DELETE FROM founder_enrollments WHERE user_id=NEW.actor_id AND test=NEW.test
      AND workspace_id=NEW.workspace_id AND payments=0;
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION founder_payment() FROM PUBLIC;
CREATE TRIGGER founder_payment AFTER UPDATE OF status ON billing_orders FOR EACH ROW EXECUTE FUNCTION founder_payment();
