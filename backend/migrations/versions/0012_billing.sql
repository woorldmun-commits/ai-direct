-- Apply as migration 0012 and append verbatim to the full schema.
CREATE TABLE billing_orders (
  id uuid PRIMARY KEY,
  workspace_id bigint REFERENCES workspaces ON DELETE SET NULL,
  actor_id bigint REFERENCES users ON DELETE SET NULL,
  subscription_id bigint REFERENCES subscriptions ON DELETE SET NULL,
  sku text NOT NULL CHECK (sku IN ('control','business','agency')),
  plan text NOT NULL CHECK (plan IN ('start','business','business_plus')),
  amount_minor bigint NOT NULL CHECK (amount_minor > 0),
  currency text NOT NULL DEFAULT 'RUB' CHECK (currency = 'RUB'),
  terms_sha256 text NOT NULL CHECK (terms_sha256 ~ '^[a-f0-9]{64}$'),
  provider_payment_id text UNIQUE,
  provider_status text CHECK (provider_status IN ('pending','waiting_for_capture','succeeded','canceled')),
  verified_at timestamptz,
  provider_body jsonb NOT NULL,
  test boolean NOT NULL,
  shop_id text NOT NULL CHECK (shop_id ~ '^[0-9]+$'),
  status text NOT NULL DEFAULT 'creating' CHECK (status IN ('creating','pending','succeeded','canceled','review_required')),
  created_at timestamptz NOT NULL DEFAULT now(),
  fulfilled_at timestamptz,
  refunded_minor bigint NOT NULL DEFAULT 0 CHECK (refunded_minor BETWEEN 0 AND amount_minor),
  CHECK (fulfilled_at IS NULL OR provider_payment_id IS NOT NULL)
);
CREATE UNIQUE INDEX billing_orders_one_pending ON billing_orders(workspace_id)
  WHERE status IN ('creating','pending','review_required');
ALTER TABLE billing_orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant ON billing_orders TO app_rw
  USING (workspace_id = app_workspace_id()) WITH CHECK (workspace_id = app_workspace_id());
CREATE POLICY system ON billing_orders TO app_system USING (true) WITH CHECK (true);
REVOKE ALL ON billing_orders FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON billing_orders TO app_rw;

CREATE FUNCTION billing_order_anonymize() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.id,NEW.sku,NEW.plan,NEW.amount_minor,NEW.currency,NEW.terms_sha256,NEW.created_at,NEW.test,NEW.shop_id)
     IS DISTINCT FROM
     (OLD.id,OLD.sku,OLD.plan,OLD.amount_minor,OLD.currency,OLD.terms_sha256,OLD.created_at,OLD.test,OLD.shop_id)
     OR (NEW.workspace_id IS DISTINCT FROM OLD.workspace_id AND NEW.workspace_id IS NOT NULL)
     OR (OLD.provider_payment_id IS NOT NULL AND NEW.provider_payment_id IS DISTINCT FROM OLD.provider_payment_id)
     OR (NEW.provider_body IS DISTINCT FROM OLD.provider_body AND NEW.provider_body <> '{}'::jsonb)
     OR (OLD.fulfilled_at IS NOT NULL AND NEW.fulfilled_at IS DISTINCT FROM OLD.fulfilled_at)
     OR NEW.refunded_minor < OLD.refunded_minor THEN
    RAISE EXCEPTION 'billing order evidence is immutable' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.workspace_id IS NULL OR NEW.actor_id IS NULL THEN
    NEW.provider_body := '{}';
    IF NEW.status IN ('creating','pending') THEN
      NEW.status := 'review_required';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER billing_order_anonymize BEFORE UPDATE ON billing_orders
  FOR EACH ROW EXECUTE FUNCTION billing_order_anonymize();
