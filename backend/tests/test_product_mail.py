from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest

from app.auth.email_config import EmailAuthConfig
from app.worker.notify import Notifier
from app.worker.product_mail_runner import finish, process_one
from test_notify import NOW, event, member, verified_email, ws  # noqa: F401
from test_schema import chain  # noqa: F401 -- fixture required by ws

CONFIG=EmailAuthConfig('https://app.example.test','synthetic-key-long-enough-for-auth-12345',
                       'smtp.example.test',smtp_from='noreply@example.test')


@pytest.fixture(autouse=True)
def isolate_pending_jobs(rw):
    rw.execute("UPDATE notifications SET status='skipped' WHERE status IN ('queued','failed')")


def test_opted_in_delivery_does_not_copy_event_payload(rw,ws):
    Notifier(rw,NOW).publish(event(rw,ws))
    sent=[]
    assert process_one(rw,CONFIG,now=NOW+timedelta(seconds=1),sender=lambda *args:sent.append(args))
    assert len(sent)==1 and sent[0][1].endswith('@example.test')
    assert 'новые рекомендации' in sent[0][2]
    assert 'issue_id' not in sent[0][3] and 'example.test/workspace/recommendations' in sent[0][3]
    assert rw.execute('SELECT status FROM notifications WHERE workspace_id=%s',(ws['ws'],)).fetchone()[0]=='sent'


def test_revoked_preference_between_queue_and_send_skips(rw,ws):
    Notifier(rw,NOW).publish(event(rw,ws))
    rw.execute('UPDATE workspace_email_preferences SET enabled=false WHERE workspace_id=%s',(ws['ws'],))
    assert process_one(rw,CONFIG,now=NOW+timedelta(seconds=1),sender=lambda *args:pytest.fail('sent after opt-out'))
    assert rw.execute('SELECT status FROM notifications WHERE workspace_id=%s',(ws['ws'],)).fetchone()[0]=='skipped'


def test_timeout_retries_with_sanitized_error(rw,ws):
    Notifier(rw,NOW).publish(event(rw,ws))
    def unavailable(*args):
        raise RuntimeError('secret-provider-message')
    process_one(rw,CONFIG,now=NOW+timedelta(seconds=1),sender=unavailable)
    row=rw.execute('SELECT status,last_error_code,attempts FROM notifications WHERE workspace_id=%s',(ws['ws'],)).fetchone()
    assert row==('failed','mail_unavailable',1)
    assert not process_one(rw,CONFIG,now=NOW+timedelta(seconds=2),sender=unavailable)
    process_one(rw,CONFIG,now=NOW+timedelta(minutes=2),sender=lambda *args:None)
    assert rw.execute('SELECT status FROM notifications WHERE workspace_id=%s',(ws['ws'],)).fetchone()[0]=='sent'


def test_stale_lease_cannot_finish_new_claim(rw,ws):
    Notifier(rw,NOW).publish(event(rw,ws))
    identity=rw.execute('SELECT id FROM notifications WHERE workspace_id=%s',(ws['ws'],)).fetchone()[0]
    old,new=uuid4(),uuid4()
    rw.execute('UPDATE notifications SET lease_token=%s WHERE id=%s',(new,identity))
    assert finish(rw,identity,old,status='sent',now=NOW)==0
    assert finish(rw,identity,new,status='sent',now=NOW)==1


def test_two_recipients_have_independent_delivery(rw,ws,db):
    member(rw,ws,db,'viewer')
    Notifier(rw,NOW).publish(event(rw,ws))
    assert rw.execute('SELECT count(*) FROM notifications WHERE workspace_id=%s',(ws['ws'],)).fetchone()[0]==2
    sent=[]
    for _ in range(2):
        assert process_one(rw,CONFIG,now=NOW+timedelta(seconds=1),sender=lambda *args:sent.append(args))
    assert len({item[1] for item in sent})==2


def test_recipient_identity_function_is_not_public_to_api(db):
    with db('app_rw') as conn,pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute('SELECT * FROM product_email_recipients(1)')


def test_enabling_mail_does_not_replay_events_before_opt_in(rw,ws):
    e=event(rw,ws,created_at=NOW-timedelta(days=7))
    Notifier(rw,NOW).publish(e)
    status,payload=rw.execute('SELECT status,payload FROM notifications WHERE workspace_id=%s',(ws['ws'],)).fetchone()
    assert status=='skipped' and payload['skip_reason']=='before_opt_in'


def test_consumer_error_is_not_hidden_by_next_heartbeat(rw,monkeypatch):
    import threading
    from app.worker import product_mail_runner as worker
    from app.worker.progress import record,status
    def unavailable(*args,**kwargs):
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(worker,'run_notifications',unavailable)
    with pytest.raises(RuntimeError):
        worker.tick(rw,CONFIG,threading.Event())
    record(rw,'product_mail',phase='mail')
    assert not status(rw,now=NOW,expected=('product_mail',))['workers']['product_mail']['healthy']
