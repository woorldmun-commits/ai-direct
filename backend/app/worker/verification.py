"""Bounded durable verification queue; only Direct get methods, no advertising writes."""
from datetime import datetime, timedelta, timezone
import psycopg
from app.auth.tokens import ConnectionRef, fresh_access_token
from app.auth.yandex_oauth import OAuthError
from app.audit.membership import METHOD, Membership, verify_membership
from app.sources.direct_params import DirectReadClient, ParamsFormatError, ParamsUnavailable, read_object_params
from app.tenancy import workspace_scope
from app.worker.guard import Skip, Task, guard, load_state
from app.worker.locks import workspace_shared

MAX_ATTEMPTS = 5

class MembershipClient(DirectReadClient):
    def call(self, service, method, params):
        result = super().call(service, method, params)
        if service == "campaigns":
            campaigns = result.get("Campaigns")
            if not isinstance(campaigns, list):
                raise ParamsFormatError("Campaigns must be a list")
            for campaign in campaigns:
                if not isinstance(campaign, dict):
                    raise ParamsFormatError("campaign must be an object")
                if "ExcludedSites" not in campaign:
                    raise ParamsFormatError("ExcludedSites is missing")
                excluded = campaign["ExcludedSites"]
                if excluded is not None and (not isinstance(excluded, dict) or not isinstance(excluded.get("Items"), list)
                        or any(not isinstance(site, str) for site in excluded["Items"])):
                    raise ParamsFormatError("ExcludedSites must contain a string list")
        return result


def due(queue, now):
    return queue.execute("""SELECT id,workspace_id FROM recommendation_verification_jobs
        WHERE finished_at IS NULL AND available_at<=%s ORDER BY available_at,id LIMIT 25""", (now,)).fetchall()


def process(conn, job_id, workspace_id, *, provider, keys, release_id, http, now, clock=lambda: datetime.now(timezone.utc)):
    assert conn.autocommit
    lock = (f"verification:{job_id}",)
    if not conn.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0))", lock).fetchone()[0]:
        return
    try:
        with workspace_scope(conn, workspace_id):
            row = conn.execute("""SELECT j.finding_id,j.done_event_id,j.attempts,j.method,i.direct_account_id,
                i.object_id,a.direct_connection_id,coalesce(a.client_login,c.yandex_login),f.action,e.created_at,a.is_selected
                FROM recommendation_verification_jobs j JOIN findings f ON f.id=j.finding_id
                JOIN issues i ON i.id=f.issue_id JOIN direct_accounts a ON a.id=i.direct_account_id
                JOIN direct_connections c ON c.id=a.direct_connection_id JOIN recommendation_events e ON e.id=j.done_event_id
                WHERE j.id=%s AND j.finished_at IS NULL AND j.available_at<=%s""", (job_id,now)).fetchone()
            if not row:
                return
            finding, done, attempts, method, account, campaign, connection, login, action, claimed, selected = row
            outcome, params, retry = None, None, None
            observed = clock()
            blocked = guard(Task.SYNC, load_state(conn, workspace_id, account, now))
            if isinstance(blocked, Skip) or not selected:
                outcome = Membership("unavailable", blocked.reason if isinstance(blocked, Skip) else "account_not_selected")
            elif method != METHOD:
                outcome = Membership("unavailable", "method_unsupported")
            else:
                try:
                    access = fresh_access_token(conn,http,provider,keys,ConnectionRef("direct",workspace_id,connection),now)
                    params = read_object_params(MembershipClient(http,access,login),campaign,action,now)
                    observed = clock()
                    if observed.tzinfo is None or observed < claimed:
                        outcome = Membership("unavailable", "read_time_invalid")
                    else:
                        outcome = verify_membership(action,params,campaign)
                    if isinstance(params, ParamsUnavailable) and params.retry_in is not None:
                        retry = min(3600,max(1,params.retry_in,60 * 2**attempts))
                except OAuthError:
                    outcome = Membership("unavailable", "token_unavailable")
                    retry = min(3600,60 * 2**attempts)
            with conn.transaction():
                workspace_shared(conn,workspace_id)
                job = conn.execute("SELECT finished_at FROM recommendation_verification_jobs WHERE id=%s FOR UPDATE", (job_id,)).fetchone()
                if not job or job[0] is not None:
                    return
                blocked = guard(Task.SYNC,load_state(conn,workspace_id,account,observed))
                current = conn.execute("""SELECT coalesce((SELECT finding_id FROM recommendation_events WHERE recommendation_id=j.recommendation_id
                    AND type='seen_again' ORDER BY id DESC LIMIT 1),r.finding_id),a.is_selected
                    FROM recommendation_verification_jobs j JOIN recommendations r ON r.id=j.recommendation_id
                    JOIN issues i ON i.id=r.issue_id JOIN direct_accounts a ON a.id=i.direct_account_id WHERE j.id=%s""", (job_id,)).fetchone()
                if isinstance(blocked,Skip) or not current or current != (finding,True):
                    outcome = Membership("unavailable", "eligibility_changed")
                    retry = None
                attempt = attempts + 1
                if retry is not None and attempt >= MAX_ATTEMPTS:
                    outcome = Membership("unavailable", "retries_exhausted")
                    retry = None
                conn.execute("""INSERT INTO recommendation_verification_reads(job_id,workspace_id,release_id,attempt,read_at,status,reason,
                    params_hash,target_count,matched_count,masked_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (job_id,workspace_id,release_id,attempt,observed,outcome.status,outcome.reason,
                     params.params_hash if params is not None and not isinstance(params,ParamsUnavailable) else None,
                     outcome.target_count,outcome.matched_count,outcome.masked_count))
                conn.execute("""UPDATE recommendation_verification_jobs SET attempts=%s,last_error=%s,
                    available_at=%s,finished_at=%s WHERE id=%s""", (attempt,outcome.reason,observed+timedelta(seconds=retry or 0),
                    None if retry else observed,job_id))
    except psycopg.OperationalError:
        raise
    except Exception:
        # Keep failure accounting under the same job lock as successful processing.
        with workspace_scope(conn,workspace_id):
            conn.execute("""UPDATE recommendation_verification_jobs SET available_at=%s,attempts=attempts+1,
                finished_at=CASE WHEN attempts>=4 THEN %s ELSE NULL END,last_error='worker_error'
                WHERE id=%s AND finished_at IS NULL AND attempts<5""", (now+timedelta(seconds=60),now,job_id))
        raise
    finally:
        conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))",lock)
