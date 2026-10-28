-- Global authentication identities; workspace RLS is not an identity boundary.
CREATE TABLE email_credentials (
 user_id bigint PRIMARY KEY REFERENCES users ON DELETE CASCADE,
 email text NOT NULL UNIQUE CHECK(length(email)<=254 AND email=lower(email)),
 password_hash text NOT NULL CHECK(length(password_hash)<=256),
 verified_at timestamptz NOT NULL DEFAULT now(),
 password_changed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE email_pending_signups (
 email text PRIMARY KEY CHECK(length(email)<=254 AND email=lower(email)),
 password_hash text NOT NULL CHECK(length(password_hash)<=256),
 token_hash bytea NOT NULL UNIQUE CHECK(length(token_hash)=32),
 expires_at timestamptz NOT NULL,
 accepted jsonb NOT NULL,
 hashes jsonb NOT NULL,
 locale text NOT NULL,
 accepted_at timestamptz NOT NULL DEFAULT now(),
 ip text,
 user_agent text
);
CREATE TABLE email_reset_tokens (
 token_hash bytea PRIMARY KEY CHECK(length(token_hash)=32),
 user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
 expires_at timestamptz NOT NULL
);
CREATE TABLE email_auth_attempts (
 operation text NOT NULL CHECK(operation IN ('login','send','confirm')),
 email_key bytea NOT NULL CHECK(length(email_key)=32),
 ip_key bytea NOT NULL CHECK(length(ip_key)=32),
 occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX email_auth_attempts_at ON email_auth_attempts(occurred_at);
CREATE INDEX email_auth_attempts_email ON email_auth_attempts(email_key,operation,occurred_at);
CREATE INDEX email_auth_attempts_ip ON email_auth_attempts(ip_key,occurred_at);
REVOKE ALL ON email_credentials,email_pending_signups,email_reset_tokens,email_auth_attempts FROM PUBLIC,app_rw,app_system;

CREATE FUNCTION email_auth_attempt(op text, ek bytea, ik bytea) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE n integer; BEGIN
 IF op NOT IN ('login','send','confirm') OR length(ek)<>32 OR length(ik)<>32 THEN RETURN false; END IF;
 PERFORM pg_advisory_xact_lock(70192387001);
 DELETE FROM email_auth_attempts WHERE occurred_at<now()-interval '1 day';
 SELECT count(*) INTO n FROM email_auth_attempts WHERE occurred_at>now()-interval '1 hour';
 IF n>=1000 THEN RETURN false; END IF;
 SELECT count(*) INTO n FROM email_auth_attempts WHERE ip_key=ik AND occurred_at>now()-interval '15 minutes';
 IF n>=100 THEN RETURN false; END IF;
 SELECT count(*) INTO n FROM email_auth_attempts WHERE email_key=ek AND operation=op
  AND occurred_at>now()-CASE WHEN op='send' THEN interval '1 hour' ELSE interval '15 minutes' END;
 IF n>=(CASE WHEN op='send' THEN 5 WHEN op='confirm' THEN 20 ELSE 10 END) THEN RETURN false; END IF;
 INSERT INTO email_auth_attempts(operation,email_key,ip_key) VALUES(op,ek,ik);
 RETURN true;
END $$;

CREATE FUNCTION email_auth_credential(address text)
RETURNS TABLE(user_id bigint,password_hash text,status text)
LANGUAGE sql SECURITY DEFINER SET search_path=public,pg_temp AS $$
 SELECT c.user_id,c.password_hash,u.status FROM email_credentials c JOIN users u ON u.id=c.user_id WHERE c.email=address
$$;

CREATE FUNCTION email_auth_signup(address text, pwd text, tok bytea, versions jsonb, digests jsonb, language text, client_ip text, agent text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('email:'||address,0));
 IF EXISTS(SELECT 1 FROM email_credentials WHERE email=address) THEN RETURN false; END IF;
 INSERT INTO email_pending_signups(email,password_hash,token_hash,expires_at,accepted,hashes,locale,ip,user_agent)
 VALUES(address,pwd,tok,now()+interval '30 minutes',versions,digests,language,client_ip,agent)
 ON CONFLICT(email) DO UPDATE SET password_hash=EXCLUDED.password_hash,token_hash=EXCLUDED.token_hash,
 expires_at=EXCLUDED.expires_at,accepted=EXCLUDED.accepted,hashes=EXCLUDED.hashes,locale=EXCLUDED.locale,
 accepted_at=now(),ip=EXCLUDED.ip,user_agent=EXCLUDED.user_agent;
 RETURN true;
END $$;

CREATE FUNCTION email_auth_pending(tok bytea)
RETURNS TABLE(email text,password_hash text,accepted jsonb,hashes jsonb,locale text,accepted_at timestamptz,ip text,user_agent text)
LANGUAGE sql SECURITY DEFINER SET search_path=public,pg_temp AS $$
 SELECT p.email,p.password_hash,p.accepted,p.hashes,p.locale,p.accepted_at,p.ip,p.user_agent
 FROM email_pending_signups p WHERE p.token_hash=tok AND p.expires_at>now()
$$;

CREATE FUNCTION email_auth_finish(tok bytea, expected_pwd text) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE p email_pending_signups%ROWTYPE; uid bigint; address text; BEGIN
 SELECT email INTO address FROM email_pending_signups WHERE token_hash=tok;
 IF address IS NULL THEN RETURN NULL; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('email:'||address,0));
 SELECT * INTO p FROM email_pending_signups WHERE token_hash=tok AND expires_at>now() FOR UPDATE;
 IF NOT FOUND OR p.password_hash<>expected_pwd THEN RETURN NULL; END IF;
 IF EXISTS(SELECT 1 FROM email_credentials WHERE email=p.email) THEN RETURN NULL; END IF;
 INSERT INTO users(email) VALUES(p.email) RETURNING id INTO uid;
 INSERT INTO email_credentials(user_id,email,password_hash) VALUES(uid,p.email,p.password_hash);
 DELETE FROM email_pending_signups WHERE email=p.email;
 RETURN uid;
END $$;

CREATE FUNCTION email_auth_login(address text,expected_pwd text,session_token bytea) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE uid bigint; BEGIN
 SELECT c.user_id INTO uid FROM email_credentials c JOIN users u ON u.id=c.user_id
  WHERE c.email=address AND c.password_hash=expected_pwd AND u.status='active' FOR UPDATE OF c,u;
 IF uid IS NULL THEN RETURN false; END IF;
 INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(session_token,uid,now()+interval '30 days');
 RETURN true;
END $$;

CREATE FUNCTION email_auth_reset_request(address text,tok bytea) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE uid bigint; BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('email:'||address,0));
 SELECT c.user_id INTO uid FROM email_credentials c JOIN users u ON u.id=c.user_id WHERE c.email=address AND u.status='active';
 IF uid IS NULL THEN RETURN false; END IF;
 DELETE FROM email_reset_tokens WHERE user_id=uid;
 INSERT INTO email_reset_tokens(token_hash,user_id,expires_at) VALUES(tok,uid,now()+interval '15 minutes');
 RETURN true;
END $$;

CREATE FUNCTION email_auth_reset_finish(tok bytea,pwd text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE uid bigint; BEGIN
 SELECT t.user_id INTO uid FROM email_reset_tokens t JOIN users u ON u.id=t.user_id
  WHERE t.token_hash=tok AND t.expires_at>now() AND u.status='active' FOR UPDATE OF t;
 IF uid IS NULL THEN RETURN false; END IF;
 PERFORM 1 FROM email_credentials WHERE user_id=uid FOR UPDATE;
 DELETE FROM email_reset_tokens WHERE user_id=uid;
 UPDATE email_credentials SET password_hash=pwd,password_changed_at=now() WHERE user_id=uid;
 DELETE FROM sessions WHERE user_id=uid;
 RETURN true;
END $$;

DO $$ DECLARE f regprocedure; BEGIN
 FOR f IN SELECT oid::regprocedure FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname LIKE 'email_auth_%' LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC',f);
  EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO app_rw',f);
 END LOOP;
END $$;

ALTER FUNCTION purge_personal_data(timestamptz) RENAME TO purge_personal_data_before_email;
REVOKE ALL ON FUNCTION purge_personal_data_before_email(timestamptz) FROM PUBLIC,app_rw,app_system,app_deleter;
CREATE FUNCTION purge_personal_data(cutoff timestamptz) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE old_n integer; n integer; total integer:=0; BEGIN
 DELETE FROM email_reset_tokens WHERE expires_at<cutoff OR user_id IN
  (SELECT id FROM users WHERE status='deactivated' AND deactivated_at<cutoff);
 GET DIAGNOSTICS n=ROW_COUNT; total:=total+n;
 DELETE FROM email_credentials WHERE user_id IN(SELECT id FROM users WHERE status='deactivated' AND deactivated_at<cutoff);
 GET DIAGNOSTICS n=ROW_COUNT; total:=total+n;
 DELETE FROM email_pending_signups WHERE expires_at<cutoff;
 GET DIAGNOSTICS n=ROW_COUNT; total:=total+n;
 DELETE FROM email_auth_attempts WHERE occurred_at<cutoff;
 GET DIAGNOSTICS n=ROW_COUNT; total:=total+n;
 old_n:=purge_personal_data_before_email(cutoff);
 IF total>0 THEN
  INSERT INTO deletion_requests(requested_by,scope,status,started_at,completed_at,verification,deleted_by)
  VALUES('system:retention','personal_data_expired','completed',now(),now(),jsonb_build_object('email_auth_records',total,'cutoff',cutoff),'purge_personal_data');
 END IF;
 RETURN old_n+total;
END $$;
REVOKE ALL ON FUNCTION purge_personal_data(timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION purge_personal_data(timestamptz) TO app_deleter;
