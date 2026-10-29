"""Offline preflight must fail closed and never echo configuration secrets."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('launch_readiness', Path(__file__).parents[2] / 'deploy/readiness.py')
readiness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readiness)


def test_empty_configuration_is_not_ready():
    result = readiness.inspect({})
    assert result['configuration_ready'] is False
    assert result['launch_approved'] is False
    assert not any(result['checks'].values())


def test_preflight_never_exposes_bad_configuration_values():
    sentinel = 'do-not-print-this-secret'
    result = readiness.inspect({'API_DATABASE_URL': sentinel, 'API_ALLOWED_ORIGINS': sentinel,
        'INROU_AUTH_HMAC_KEY': sentinel, 'INROU_MAIL_API_KEY': sentinel})
    assert sentinel not in json.dumps(result)
    assert not result['configuration_ready']


def test_frontend_origin_must_match_https_application_at_build_time():
    for site in ['', 'http://localhost:10000', 'https://other.example.test']:
        assert not readiness.inspect({'INROU_APP_ORIGIN': 'https://example.test',
            'NEXT_PUBLIC_SITE_URL': site})['checks']['frontend_build_origin_configuration']
    assert readiness.inspect({'INROU_APP_ORIGIN': 'https://example.test',
        'NEXT_PUBLIC_SITE_URL': 'https://example.test'})['checks']['frontend_build_origin_configuration']


def test_signed_ip_preflight_rejects_chains_and_unconfigured_keys():
    for header, key in [('x-forwarded-for', 'x' * 32), ('x-real-ip', ''), ('bad\nheader', 'x' * 32)]:
        assert not readiness.inspect({'INROU_CLIENT_IP_HEADER': header,
            'API_PROXY_HMAC_KEY': key})['checks']['signed_client_ip_configuration']
    result = readiness.inspect({'INROU_CLIENT_IP_HEADER': 'x-real-ip', 'API_PROXY_HMAC_KEY': 'x' * 32})
    assert result['checks']['signed_client_ip_configuration']
    assert 'ingress_overwrites_spoofed_ip' in result['manual_checks_required']
    assert not result['launch_approved']


def test_draft_cannot_be_marked_ready_even_by_its_hash():
    raw = readiness.text_path('offer', readiness.VERSIONS['offer'][-1]).read_bytes()
    env = {'API_DATABASE_URL': 'postgresql://app_rw@localhost/test',
        'API_ALLOWED_ORIGINS': 'https://example.test',
        'API_SIGNUP_APPROVED_HASHES': json.dumps({'offer': readiness.hashlib.sha256(raw).hexdigest()})}
    assert not readiness.inspect(env)['checks']['approved_offer']


def test_billing_requires_exact_published_offer(monkeypatch, tmp_path):
    import pytest
    import app.api.settings as settings
    from app.billing.provider import BillingConfig
    raw = b'Synthetic approved contract for local test only.'
    document = tmp_path / 'offer.md'
    document.write_bytes(raw)
    monkeypatch.setattr(settings, 'text_path', lambda *a: document)
    digest = readiness.hashlib.sha256(raw).hexdigest()
    billing = BillingConfig('12345', 'synthetic-secret', 'https://example.test', digest, 1, 1)
    values = dict(database_url='postgresql://app_rw@localhost/test', allowed_origins=frozenset({'https://example.test'}), billing=billing)
    with pytest.raises(settings.SettingsError, match='exact published'):
        settings.Settings(**values)
    assert settings.Settings(**values, signup_approved_hashes={'offer': digest}).billing is billing
    document.write_text('ЗАГЛУШКА', encoding='utf-8')
    from dataclasses import replace
    draft = readiness.hashlib.sha256(document.read_bytes()).hexdigest()
    with pytest.raises(settings.SettingsError, match='exact published'):
        settings.Settings(**{**values, 'billing': replace(billing, terms_sha256=draft)}, signup_approved_hashes={'offer': draft})
