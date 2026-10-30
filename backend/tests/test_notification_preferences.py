import pytest

from app.api import create_app
from test_api_support import client_for, cookie, session, settings, user
from test_email_auth import browser, verified  # noqa: F401 -- fixture
from test_schema import new_workspace


def test_service_mail_is_explicitly_opted_in_and_can_be_disabled(browser):
    verified(browser)
    workspace=browser.get('/api/v1/me').json()['organizations'][0]['workspaces'][0]['id']
    url=f'/api/v1/workspaces/{workspace}/email-preference'
    assert browser.get(url).json()=={'enabled':False,'email_verified':True,'delivery_configured':False}
    for enabled in (True,False):
        response=browser.post(url,headers={'Origin':'https://app.example.test'},json={'enabled':enabled})
        assert response.status_code==200 and response.json()['enabled'] is enabled
        assert browser.get(url).json()['enabled'] is enabled


def test_unverified_identity_cannot_enable_service_mail(db,rw):
    identity=user(rw)
    workspace=new_workspace(rw,user=identity)
    with client_for(create_app(settings(db))) as client:
        headers={'Origin':'https://app.example.test',**cookie(session(rw,identity))}
        url=f'/api/v1/workspaces/ws_{workspace}/email-preference'
        assert client.get(url,headers=headers).json()['email_verified'] is False
        assert client.post(url,headers=headers,json={'enabled':True}).status_code==409
        assert client.post(url,headers=headers,json={'enabled':False}).status_code==200


@pytest.mark.parametrize('bad',['true',1,None,[],{}])
def test_service_mail_preference_is_strict_and_tenant_scoped(browser,rw,bad):
    verified(browser)
    workspace=browser.get('/api/v1/me').json()['organizations'][0]['workspaces'][0]['id']
    url=f'/api/v1/workspaces/{workspace}/email-preference'
    assert browser.post(url,headers={'Origin':'https://app.example.test'},json={'enabled':bad}).status_code==400
    assert browser.post(url,headers={'Origin':'https://foreign.example'},json={'enabled':True}).status_code==403
    foreign=new_workspace(rw)
    assert browser.get(f'/api/v1/workspaces/ws_{foreign}/email-preference').status_code==404
