import hashlib
import hmac
import time

import pytest

from app.api.proxy_client import verified_client

KEY='synthetic-proxy-key-for-tests-only-123456'


def signed(ip='203.0.113.7', stamp=None, path='/api/v1/auth/email/login'):
    value=f'{int(time.time()) if stamp is None else stamp}:{ip}'
    signature=hmac.new(KEY.encode(),f'POST\n{path}\n{value}'.encode(),hashlib.sha256).hexdigest()
    return [(b'x-inrou-client',value.encode()),(b'x-inrou-proxy-signature',signature.encode())]


@pytest.mark.parametrize('ip',['203.0.113.7','2001:db8::1'])
def test_valid_frontend_signature(ip):
    assert verified_client(signed(ip),'POST','/api/v1/auth/email/login',KEY)==ip


def test_unauthenticated_and_replayed_forwarded_headers_are_ignored():
    path='/api/v1/auth/email/login'
    assert verified_client([(b'x-forwarded-for',b'203.0.113.7')],'POST',path,KEY) is None
    assert verified_client(signed(),'POST',path,'wrong-key') is None
    assert verified_client(signed(),'POST',path,'') is None
    assert verified_client(signed(stamp=int(time.time())-61),'POST',path,KEY) is None
    assert verified_client(signed(stamp=int(time.time())+61),'POST',path,KEY) is None
    assert verified_client(signed(path='/another'),'POST',path,KEY) is None
    assert verified_client(signed(),'GET',path,KEY) is None
    assert verified_client(signed()+signed(),'POST',path,KEY) is None
    assert verified_client(signed('not-an-ip'),'POST',path,KEY) is None


def test_middleware_uses_only_the_verified_visitor():
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    from app.api.middleware import BoundaryMiddleware
    from app.api.settings import Settings
    app=FastAPI()
    app.add_middleware(BoundaryMiddleware,settings=Settings(database_url='unused',
        allowed_origins=frozenset({'https://app.example'}),proxy_hmac_key=KEY))
    @app.post('/api/v1/auth/email/login')
    def peer(request: Request):
        return {'ip':request.client.host}
    with TestClient(app) as client:
        headers={k.decode():v.decode() for k,v in signed()}
        headers['Origin']='https://app.example'
        assert client.post('/api/v1/auth/email/login',headers=headers).json()['ip']=='203.0.113.7'
        headers['X-Inrou-Client']=f'{int(time.time())}:203.0.113.99'
        assert client.post('/api/v1/auth/email/login',headers=headers).json()['ip']=='testclient'
