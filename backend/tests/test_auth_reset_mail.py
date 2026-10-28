"""Global reset outbox: real DB, synthetic transport, no external delivery."""
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest

from app.auth.email_config import EmailAuthConfig
from app.auth.email_password import mail_token, token_hash
from app.worker.auth_mail_runner import process_one
from app.worker.retention import purge_personal_data
from test_email_auth import browser, post, verified  # noqa: F401

CONFIG = EmailAuthConfig('https://example.test', 'synthetic-auth-hmac-key-long-enough-12345',
                         'smtp.example.test', smtp_from='noreply@example.test')


def test_same_reset_response_and_durable_retry_on_provider_failure(browser, db, caplog):
    verified(browser)
    before = len(browser.mail)
    def fail(*args):
        raise RuntimeError('synthetic-private-recipient-and-token')
    browser.app.state.email_sender = fail
    for address in (browser.email, 'unknown-reset@example.test'):
        response = post(browser, 'reset-request', {'email': address})
        assert response.status_code == 202 and response.json() == {'status': 'check_email'}
    assert len(browser.mail) == before
    browser.drain_reset_mail()
    with db('app_migrator') as conn:
        pending = conn.execute('SELECT id,attempts,prepared FROM email_reset_mail WHERE recipient=%s', (browser.email,)).fetchone()
        assert pending and pending[1:] == (1, True)
        assert conn.execute("SELECT count(*) FROM email_reset_mail WHERE recipient='unknown-reset@example.test'").fetchone()[0] == 0
        conn.execute('UPDATE email_reset_mail SET available_at=now() WHERE id=%s', (pending[0],))
    browser.app.state.email_sender = lambda *args: browser.mail.append(args)
    browser.drain_reset_mail()
    assert len(browser.mail) == before + 1
    with db('app_migrator') as conn:
        assert conn.execute('SELECT count(*) FROM email_reset_mail WHERE id=%s', (pending[0],)).fetchone()[0] == 0
    assert 'synthetic-private' not in caplog.text and browser.email not in caplog.text


def test_queue_atomicity_privacy_expiry_and_lease_fencing(db):
    job = uuid4()
    with db('app_rw') as conn:
        with pytest.raises(RuntimeError), conn.transaction():
            conn.execute('SELECT enqueue_email_reset_mail(%s,%s)', (job, 'rollback@example.test'))
            raise RuntimeError('rollback')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM email_reset_mail')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM claim_email_reset_mail()')
        conn.execute('SELECT enqueue_email_reset_mail(%s,%s)', (job, 'leased@example.test'))
    with db('app_system') as first, db('app_system') as second:
        claimed = first.execute('SELECT * FROM claim_email_reset_mail()').fetchone()
        assert claimed and claimed[0] == job
        assert second.execute('SELECT * FROM claim_email_reset_mail()').fetchone() is None
        with db('app_migrator') as owner:
            owner.execute("UPDATE email_reset_mail SET locked_until=now()-interval '1 second' WHERE id=%s", (job,))
        reclaimed = second.execute('SELECT * FROM claim_email_reset_mail()').fetchone()
        assert reclaimed[0] == job and reclaimed[1] != claimed[1]
        first.execute('SELECT finish_email_reset_mail(%s,%s,true)', claimed[:2])
        assert first.execute('SELECT * FROM prepare_email_reset_mail(%s,%s,%s)', (*claimed[:2], token_hash('x'*43))).fetchone() is None
        with db('app_migrator') as owner:
            assert owner.execute('SELECT count(*) FROM email_reset_mail WHERE id=%s', (job,)).fetchone()[0] == 1
            owner.execute("UPDATE email_reset_mail SET expires_at=now()-interval '1 second' WHERE id=%s", (job,))
        assert not process_one(second, CONFIG, sender=lambda *args: pytest.fail('expired mail'))
    with db('app_migrator') as owner:
        assert owner.execute('SELECT count(*) FROM email_reset_mail WHERE id=%s', (job,)).fetchone()[0] == 0


def test_job_token_is_stable_distinct_domain_separated_and_never_stored(db):
    job, other = uuid4(), uuid4()
    value = mail_token(CONFIG.hmac_key, job, 'reset')
    assert len(value) == 43 and value == mail_token(CONFIG.hmac_key, job, 'reset')
    assert value != mail_token(CONFIG.hmac_key, other, 'reset')
    assert value != mail_token(CONFIG.hmac_key, job, 'verify')
    with pytest.raises(ValueError):
        mail_token(CONFIG.hmac_key, job, 'other')
    assert value != mail_token(replace(CONFIG, hmac_key='other-synthetic-hmac-key-long-enough').hmac_key, job, 'reset')
    with db('app_rw') as conn:
        conn.execute('SELECT enqueue_email_reset_mail(%s,%s)', (job, 'expired@example.test'))
    with db('app_migrator') as conn:
        row = conn.execute('SELECT row_to_json(q)::text FROM email_reset_mail q WHERE id=%s', (job,)).fetchone()[0]
        assert value not in row and 'token=' not in row
        conn.execute("UPDATE email_reset_mail SET expires_at=now()-interval '1 second' WHERE id=%s", (job,))
        now = conn.execute('SELECT now()').fetchone()[0]
    with db('app_deleter') as conn:
        assert purge_personal_data(conn, now=now) >= 1
    with db('app_migrator') as conn:
        assert conn.execute('SELECT count(*) FROM email_reset_mail WHERE id=%s', (job,)).fetchone()[0] == 0


def test_latest_reset_request_supersedes_claimed_older_job(browser, db):
    verified(browser)
    old, latest = uuid4(), uuid4()
    with db('app_rw') as api, db('app_system') as worker:
        api.execute('SELECT enqueue_email_reset_mail(%s,%s)', (old, browser.email))
        old_lease = worker.execute('SELECT * FROM claim_email_reset_mail()').fetchone()
        assert old_lease[0] == old
        api.execute('SELECT enqueue_email_reset_mail(%s,%s)', (latest, browser.email))
        latest_lease = worker.execute('SELECT * FROM claim_email_reset_mail()').fetchone()
        assert latest_lease[0] == latest
        config = browser.app.state.settings.email_auth
        latest_digest = token_hash(mail_token(config.hmac_key, latest, 'reset'))
        ready = worker.execute('SELECT * FROM prepare_email_reset_mail(%s,%s,%s)',
                               (*latest_lease[:2], latest_digest)).fetchone()
        assert ready == (browser.email, True)
        assert worker.execute('SELECT * FROM prepare_email_reset_mail(%s,%s,%s)',
            (*old_lease[:2], token_hash(mail_token(config.hmac_key, old, 'reset')))).fetchone() is None
        worker.execute('SELECT finish_email_reset_mail(%s,%s,true)', old_lease[:2])
        with db('app_migrator') as owner:
            assert owner.execute('SELECT token_hash FROM email_reset_tokens t JOIN email_credentials c ON c.user_id=t.user_id WHERE c.email=%s',
                                 (browser.email,)).fetchone()[0] == latest_digest
            assert owner.execute('SELECT count(*) FROM email_reset_mail WHERE id=%s', (latest,)).fetchone()[0] == 1
        worker.execute('SELECT finish_email_reset_mail(%s,%s,true)', latest_lease[:2])


def test_registration_delivery_failures_do_not_identify_existing_accounts(browser, db, caplog):
    verified(browser)
    before=len(browser.mail)
    def fail(*args):
        raise RuntimeError('private-address-and-link')
    browser.app.state.email_sender=fail
    fresh='fresh-signup@example.test'
    for address in (browser.email,fresh):
        response=post(browser,'register',{'email':address,'password':'Synthetic password 174!',
                                         'accepted':{'offer':'2026-10-01','pd_consent':'2026-10-01'}})
        assert response.status_code==202 and response.json()=={'status':'check_email'}
    assert len(browser.mail)==before
    browser.drain_reset_mail()
    with db('app_migrator') as conn:
        row=conn.execute("SELECT q.id,q.expires_at,p.expires_at FROM email_reset_mail q JOIN email_pending_signups p ON p.email=q.recipient WHERE q.recipient=%s AND q.purpose='verify'",(fresh,)).fetchone()
        assert row and row[1]==row[2]
        assert conn.execute('SELECT count(*) FROM email_reset_mail WHERE recipient=%s',(browser.email,)).fetchone()[0]==0
        conn.execute('UPDATE email_reset_mail SET available_at=now() WHERE id=%s',(row[0],))
    browser.app.state.email_sender=lambda *args:browser.mail.append(args)
    browser.drain_reset_mail()
    assert len(browser.mail)==before+1 and browser.mail[-1][0]==fresh and browser.mail[-1][1]=='verify'
    assert '/verify-email#token=' in browser.mail[-1][2]
    assert 'private-address-and-link' not in caplog.text and fresh not in caplog.text


def test_signup_and_queued_mail_rollback_together(browser, monkeypatch, db):
    from contextlib import contextmanager
    from app.api import email_auth
    original=email_auth._connection
    class RejectQueue:
        def __init__(self,conn): self.conn=conn
        def execute(self,query,*args):
            if 'enqueue_email_verify_mail' in query:
                raise psycopg.OperationalError('synthetic-private-queue-failure')
            return self.conn.execute(query,*args)
    @contextmanager
    def connection(request):
        with original(request) as conn:
            yield RejectQueue(conn)
    monkeypatch.setattr(email_auth,'_connection',connection)
    response=post(browser,'register',{'email':browser.email,'password':'Synthetic password 174!',
                     'accepted':{'offer':'2026-10-01','pd_consent':'2026-10-01'}})
    assert response.status_code==503 and 'synthetic-private' not in response.text
    with db('app_migrator') as conn:
        assert conn.execute('SELECT count(*) FROM email_pending_signups WHERE email=%s',(browser.email,)).fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM email_reset_mail WHERE recipient=%s',(browser.email,)).fetchone()[0]==0
