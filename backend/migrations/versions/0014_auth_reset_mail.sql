-- Authentication mail is global private data; delivery is separate from HTTP requests.
CREATE TABLE email_reset_mail (
 id uuid PRIMARY KEY,
 recipient text NOT NULL CHECK(length(recipient)<=254 AND recipient=lower(recipient)),
 purpose text NOT NULL DEFAULT 'reset' CHECK(purpose IN ('reset','verify')),
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL DEFAULT now()+interval '15 minutes',
 available_at timestamptz NOT NULL DEFAULT now(),
 locked_until timestamptz,
 lease_token uuid,
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),
 prepared boolean NOT NULL DEFAULT false
);
CREATE INDEX email_reset_mail_due ON email_reset_mail(available_at,created_at);
REVOKE ALL ON email_reset_mail FROM PUBLIC,app_rw,app_system,app_token,app_deleter;

CREATE FUNCTION enqueue_email_reset_mail(job uuid,address text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('reset-mail:'||address,0));
 DELETE FROM email_reset_mail WHERE recipient=address AND purpose='reset';
 INSERT INTO email_reset_mail(id,recipient) VALUES(job,address);
END $$;
REVOKE ALL ON FUNCTION enqueue_email_reset_mail(uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION enqueue_email_reset_mail(uuid,text) TO app_rw;

CREATE FUNCTION enqueue_email_verify_mail(job uuid,address text,token_digest bytea) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('verify-mail:'||address,0));
 DELETE FROM email_reset_mail WHERE recipient=address AND purpose='verify';
 INSERT INTO email_reset_mail(id,recipient,purpose,expires_at)
 SELECT job,address,'verify',p.expires_at FROM email_pending_signups p
 WHERE p.email=address AND p.token_hash=token_digest AND p.expires_at>now();
 IF NOT FOUND THEN RAISE EXCEPTION 'Pending signup unavailable'; END IF;
END $$;
REVOKE ALL ON FUNCTION enqueue_email_verify_mail(uuid,text,bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION enqueue_email_verify_mail(uuid,text,bytea) TO app_rw;

CREATE FUNCTION purge_email_reset_mail(expired_before timestamptz) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE n integer; BEGIN
 DELETE FROM email_reset_mail WHERE expires_at<=expired_before;
 GET DIAGNOSTICS n=ROW_COUNT;
 IF n>0 THEN
  INSERT INTO deletion_requests(requested_by,scope,status,started_at,completed_at,verification,deleted_by)
  VALUES('system:retention','personal_data_expired','completed',now(),now(),
   jsonb_build_object('email_reset_mail',n,'cutoff',expired_before),'purge_email_reset_mail');
 END IF;
 RETURN n;
END $$;
REVOKE ALL ON FUNCTION purge_email_reset_mail(timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION purge_email_reset_mail(timestamptz) TO app_deleter;

CREATE FUNCTION claim_email_reset_mail() RETURNS TABLE(job_id uuid,lease uuid,mail_purpose text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE selected uuid; BEGIN
 PERFORM purge_email_reset_mail(now());
 SELECT q.id INTO selected FROM email_reset_mail q
 WHERE q.available_at<=now() AND q.expires_at>now()
  AND (q.locked_until IS NULL OR q.locked_until<=now())
 ORDER BY q.created_at,q.id LIMIT 1 FOR UPDATE SKIP LOCKED;
 IF selected IS NULL THEN RETURN; END IF;
 RETURN QUERY UPDATE email_reset_mail q SET locked_until=now()+interval '1 minute',
  lease_token=gen_random_uuid(),attempts=q.attempts+1
 WHERE q.id=selected RETURNING q.id,q.lease_token,q.purpose;
END $$;
REVOKE ALL ON FUNCTION claim_email_reset_mail() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION claim_email_reset_mail() TO app_system;

CREATE FUNCTION prepare_email_reset_mail(job uuid,lease uuid,token_digest bytea)
RETURNS TABLE(address text,should_send boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE q email_reset_mail%ROWTYPE; required boolean; BEGIN
 IF length(token_digest)<>32 THEN RAISE EXCEPTION 'Invalid token digest'; END IF;
 SELECT * INTO q FROM email_reset_mail m WHERE m.id=job AND m.lease_token=lease
  AND m.locked_until>now() AND m.expires_at>now() FOR UPDATE;
 IF NOT FOUND THEN RETURN; END IF;
 IF q.purpose='verify' THEN
  SELECT EXISTS(SELECT 1 FROM email_pending_signups p WHERE p.email=q.recipient
   AND p.token_hash=token_digest AND p.expires_at>now()) INTO required;
  UPDATE email_reset_mail SET prepared=true WHERE id=job;
 ELSIF NOT q.prepared THEN
  required:=email_auth_reset_request(q.recipient,token_digest);
  IF required THEN
   UPDATE email_reset_tokens SET expires_at=least(expires_at,q.expires_at) WHERE token_hash=token_digest;
  END IF;
  UPDATE email_reset_mail SET prepared=true WHERE id=job;
 ELSE
  SELECT EXISTS(SELECT 1 FROM email_reset_tokens t JOIN email_credentials c ON c.user_id=t.user_id
   JOIN users u ON u.id=t.user_id WHERE t.token_hash=token_digest AND t.expires_at>now()
   AND c.email=q.recipient AND u.status='active') INTO required;
 END IF;
 RETURN QUERY SELECT q.recipient,required;
END $$;
REVOKE ALL ON FUNCTION prepare_email_reset_mail(uuid,uuid,bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION prepare_email_reset_mail(uuid,uuid,bytea) TO app_system;

CREATE FUNCTION finish_email_reset_mail(job uuid,lease uuid,succeeded boolean) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
 IF succeeded THEN
  DELETE FROM email_reset_mail WHERE id=job AND lease_token=lease;
 ELSE
  UPDATE email_reset_mail SET locked_until=NULL,lease_token=NULL,
   available_at=now()+least(60,power(2,least(attempts,6))) * interval '1 second'
  WHERE id=job AND lease_token=lease;
 END IF;
END $$;
REVOKE ALL ON FUNCTION finish_email_reset_mail(uuid,uuid,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION finish_email_reset_mail(uuid,uuid,boolean) TO app_system;
