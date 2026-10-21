import json
import httpx
import pytest
from app.auth import email_config
from app.auth.email_config import EmailAuthConfig, send


def test_unisender_transport_and_rejected_delivery(monkeypatch):
    requests = []
    config = EmailAuthConfig('https://example.test', 'x'*32, smtp_from='noreply@example.test',
                             provider='unisender', api_key='synthetic-test-key')
    client_type = httpx.Client
    status = {'status': 'success'}

    def deliver(request):
        requests.append(request)
        return httpx.Response(200, json=status)

    def client(**kwargs):
        assert kwargs == {'timeout': 10, 'follow_redirects': False, 'trust_env': False}
        return client_type(transport=httpx.MockTransport(deliver), **kwargs)

    monkeypatch.setattr(email_config.httpx, 'Client', client)
    send(config, 'recipient@example.test', 'verify', 'https://example.test/verify-email#token=synthetic')
    request = requests[0]
    assert str(request.url) == 'https://goapi.unisender.ru/ru/transactional/api/v1/email/send.json'
    assert request.headers['x-api-key'] == config.api_key
    message = json.loads(request.content)['message']
    assert message['recipients'] == [{'email': 'recipient@example.test'}]
    assert message['track_links'] == message['track_read'] == 0
    assert '#token=synthetic' in message['body']['plaintext']
    status['status'] = 'error'
    status['message'] = 'provider details must stay private'
    with pytest.raises(RuntimeError, match='^Mail delivery unavailable$'):
        send(config, 'recipient@example.test', 'verify', 'https://example.test/verify-email#token=synthetic')
    assert 'synthetic-test-key' not in repr(config)


def test_unisender_requires_key_and_unknown_provider_rejected():
    for provider in ('unisender', 'unknown'):
        with pytest.raises(ValueError):
            EmailAuthConfig('https://example.test', 'x'*32, smtp_from='noreply@example.test', provider=provider)
    config = EmailAuthConfig.from_env({'REKVERO_EMAIL_ENABLED': 'true',
        'REKVERO_EMAIL_ORIGIN': 'https://example.test', 'REKVERO_AUTH_HMAC_KEY': 'x'*32,
        'REKVERO_MAIL_PROVIDER': 'unisender', 'REKVERO_MAIL_API_KEY': 'synthetic-test-key',
        'REKVERO_SMTP_FROM': 'noreply@example.test'})
    assert config.provider == 'unisender' and config.smtp_host == ''
