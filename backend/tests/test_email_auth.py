"""Real disposable PostgreSQL; email transport and recipient addresses are synthetic."""
from dataclasses import replace
from urllib.parse import urlsplit,parse_qs
import itertools
import pytest
import psycopg
from app.api import create_app
from app.api.settings import SettingsError
from app.auth.email_config import EmailAuthConfig
from app.auth.email_password import normalize_email,password_hash,password_matches
from app.legal.documents import text_sha256
from app.worker.auth_mail_runner import process_one
from test_api_support import settings,client_for,ORIGIN,user  # noqa: F401

PASSWORD='Synthetic password 174!'
NEW_PASSWORD='Different synthetic password 285!'
COUNTER=itertools.count(1)
ACCEPTED={'offer':'2026-10-01','pd_consent':'2026-10-01'}

@pytest.fixture
def browser(db):
    config=EmailAuthConfig(ORIGIN,'synthetic-hmac-key-long-enough-123456','smtp.example.test',smtp_from='noreply@example.test')
    app=create_app(settings(db,email_auth=config,signup_approved_hashes={k:text_sha256(k,v) for k,v in ACCEPTED.items()}))
    mail=[]
    app.state.email_sender=lambda *args:mail.append(args)
    with client_for(app) as client:
        client.mail=mail
        client.email=f'person{next(COUNTER)}@example.test'
        def drain():
            with db('app_system') as conn:
                for _ in range(25):
                    if not process_one(conn, config, sender=app.state.email_sender):
                        break
        client.drain_reset_mail=drain
        yield client

def post(client,path,body):
    return client.post('/api/v1/auth/email/'+path,json=body,headers={'Origin':ORIGIN})

def register(client,email=None,password=PASSWORD):
    email=email or client.email
    response=post(client,'register',{'email':email,'password':password,'accepted':ACCEPTED})
    if response.status_code==202:
        client.drain_reset_mail()
    return response

def token(client):
    return parse_qs(urlsplit(client.mail[-1][2]).fragment)['token'][0]

def verified(client,email=None):
    assert register(client,email).status_code==202
    r=post(client,'verify',{'token':token(client),'password':PASSWORD})
    assert r.status_code==200,r.text
    return r

def test_registration_requires_mail_proof_and_creates_empty_workspace(browser,db):
    assert register(browser,browser.email.upper()).status_code==202
    assert browser.get('/api/v1/me').status_code==401
    with db('app_migrator') as conn:
        row=conn.execute('SELECT password_hash,token_hash FROM email_pending_signups WHERE email=%s',(browser.email,)).fetchone()
        assert row and row[0]!=PASSWORD and len(row[1])==32
    proof=token(browser)
    assert '/verify-email#token=' in browser.mail[0][2]
    assert post(browser,'verify',{'token':proof,'password':'Wrong password 123'}).status_code==400
    r=post(browser,'verify',{'token':proof,'password':PASSWORD})
    assert r.status_code==200 and 'httponly' in r.headers['set-cookie'].lower()
    me=browser.get('/api/v1/me')
    assert me.status_code==200 and len(me.json()['organizations'])==1
    assert post(browser,'verify',{'token':proof,'password':PASSWORD}).status_code==400
    with db('app_migrator') as conn:
        assert conn.execute("SELECT count(*) FROM email_credentials WHERE email=%s",(browser.email,)).fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM legal_acceptances WHERE user_id=(SELECT user_id FROM email_credentials WHERE email=%s)',(browser.email,)).fetchone()[0]==2

def test_login_and_failed_attempts_commit(browser,db):
    verified(browser)
    for _ in range(3):
        assert post(browser,'login',{'email':browser.email.upper(),'password':'Wrong password 123'}).status_code==401
    with db('app_migrator') as conn:
        assert conn.execute("SELECT count(*) FROM email_auth_attempts WHERE operation='login'").fetchone()[0]>=3
    assert post(browser,'login',{'email':browser.email,'password':PASSWORD}).status_code==200
    for _ in range(6):
        assert post(browser,'login',{'email':browser.email,'password':'Wrong password 123'}).status_code==401
    assert post(browser,'login',{'email':browser.email,'password':PASSWORD}).status_code==429

def test_existing_address_generic_and_no_yandex_autolink(browser,db):
    with db('app_migrator') as conn:
        legacy=conn.execute("INSERT INTO users(email) VALUES(%s) RETURNING id",(browser.email,)).fetchone()[0]
    verified(browser)
    assert register(browser).json()=={'status':'check_email'}
    assert len(browser.mail)==1
    with db('app_migrator') as conn:
        assert conn.execute("SELECT user_id FROM email_credentials WHERE email=%s",(browser.email,)).fetchone()[0]!=legacy

def test_reset_revokes_sessions_is_one_use_and_does_not_login(browser):
    verified(browser)
    assert post(browser,'reset-request',{'email':browser.email}).status_code==202
    browser.drain_reset_mail()
    reset_token=token(browser)
    assert '/reset-password#token=' in browser.mail[-1][2]
    assert post(browser,'reset',{'token':reset_token,'password':NEW_PASSWORD}).status_code==200
    assert browser.get('/api/v1/me').status_code==401
    assert post(browser,'reset',{'token':reset_token,'password':PASSWORD}).status_code==400
    assert post(browser,'login',{'email':browser.email,'password':PASSWORD}).status_code==401
    assert post(browser,'login',{'email':browser.email,'password':NEW_PASSWORD}).status_code==200

def test_unknown_address_and_yandex_only_reset_are_generic(browser,db):
    with db('app_migrator') as conn:
        conn.execute("INSERT INTO users(email) VALUES('legacy@example.test')")
    for address in ('unknown@example.test','legacy@example.test'):
        assert post(browser,'reset-request',{'email':address}).status_code==202
        assert post(browser,'login',{'email':address,'password':PASSWORD}).status_code==401
    browser.drain_reset_mail()
    assert browser.mail==[]

def test_csrf_unconfigured_and_no_get_consumption(browser,db):
    assert browser.post('/api/v1/auth/email/register',json={'email':'p@example.test','password':PASSWORD,'accepted':ACCEPTED}).status_code==403
    assert browser.get('/api/v1/auth/email/verify').status_code==405
    with client_for(create_app(settings(db))) as disabled:
        assert disabled.get('/api/v1/auth/config').json()=={'email_enabled':False}
        assert register(disabled,'disabled@example.test').status_code==503

def test_legal_revocation_and_expired_token(browser,db):
    assert register(browser).status_code==202
    proof=token(browser)
    config=browser.app.state.settings
    browser.app.state.settings=replace(config,signup_approved_hashes={})
    assert post(browser,'verify',{'token':proof,'password':PASSWORD}).status_code==503
    browser.app.state.settings=config
    with db('app_migrator') as conn:
        conn.execute("UPDATE email_pending_signups SET expires_at=now()-interval '1 second' WHERE email=%s",(browser.email,))
    assert post(browser,'verify',{'token':proof,'password':PASSWORD}).status_code==400

def test_smtp_failure_keeps_accepted_signup_mail_durable(browser,db):
    def fail(*args): raise RuntimeError('synthetic private error')
    browser.app.state.email_sender=fail
    response=register(browser)
    assert response.status_code==202 and 'private' not in response.text
    assert browser.mail==[]
    with db('app_migrator') as conn:
        assert conn.execute("SELECT attempts FROM email_reset_mail WHERE recipient=%s AND purpose='verify'",
                            (browser.email,)).fetchone()[0]>=1
    browser.app.state.email_sender=lambda *args:browser.mail.append(args)
    with db('app_migrator') as conn:
        conn.execute('UPDATE email_reset_mail SET available_at=now() WHERE recipient=%s',(browser.email,))
    browser.drain_reset_mail()

def test_direct_auth_tables_are_private_and_purge_clears_credentials(browser,db):
    verified(browser)
    with db('app_rw') as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM email_credentials')
    with db('app_migrator') as conn:
        conn.execute("UPDATE users SET status='deactivated',deactivated_at=now()-interval '2 days' WHERE email=%s",(browser.email,))
    with db('app_deleter') as conn:
        conn.execute("SELECT purge_personal_data(now()-interval '1 day')")
    with db('app_migrator') as conn:
        assert conn.execute('SELECT count(*) FROM email_credentials WHERE email=%s',(browser.email,)).fetchone()[0]==0

@pytest.mark.parametrize('bad',['bad','a..b@example.test','a@-bad.test','x\r\ny@example.test','x@bad..test'])
def test_email_rejected(bad):
    with pytest.raises(ValueError):
        normalize_email(bad)

def test_scrypt_and_configuration():
    assert normalize_email(' Person@EXAMPLE.test ')=='person@example.test'
    h=password_hash(PASSWORD)
    assert h!=PASSWORD and password_matches(PASSWORD,h) and not password_matches(NEW_PASSWORD,h)
    with pytest.raises(ValueError):
        password_hash('short')
    with pytest.raises(ValueError):
        EmailAuthConfig('https://evil.test/path','x'*32,'smtp',smtp_from='a@example.test')
    with pytest.raises(ValueError):
        EmailAuthConfig.from_env({'INROU_EMAIL_ENABLED':'true'})
