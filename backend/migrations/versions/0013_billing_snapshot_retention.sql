-- Request email is needed only within the provider's safe creation replay window.
CREATE FUNCTION purge_billing_request_snapshots(cutoff timestamptz, batch_size integer) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE n integer;
BEGIN
  IF cutoff IS NULL OR cutoff > statement_timestamp()-interval '24 hours'
     OR batch_size IS NULL OR batch_size NOT BETWEEN 1 AND 10000 THEN
    RAISE EXCEPTION 'invalid billing retention boundary';
  END IF;
  WITH expired AS (
    SELECT id FROM billing_orders WHERE created_at < cutoff AND provider_body <> '{}'::jsonb
    ORDER BY created_at,id LIMIT batch_size FOR UPDATE SKIP LOCKED
  )
  UPDATE billing_orders o SET provider_body='{}',
    status=CASE WHEN o.status='creating' THEN 'review_required' ELSE o.status END
    FROM expired WHERE o.id=expired.id;
  GET DIAGNOSTICS n=ROW_COUNT;
  IF n>0 THEN
    INSERT INTO deletion_requests(requested_by,scope,status,started_at,completed_at,verification,deleted_by)
    VALUES('system:retention','personal_data_expired','completed',now(),now(),
      jsonb_build_object('billing_request_snapshots',n,'cutoff',cutoff),'purge_billing_request_snapshots');
  END IF;
  RETURN n;
END $$;
REVOKE ALL ON FUNCTION purge_billing_request_snapshots(timestamptz,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION purge_billing_request_snapshots(timestamptz,integer) TO app_deleter;
