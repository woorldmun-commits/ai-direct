"""Offline configuration preflight; never sends mail, charges or reads customer data."""
import hashlib
import hmac
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.api.settings import (
    Settings,
)
from app.legal.documents import VERSIONS, text_path


def inspect(env):
    checks = {}
    try:
        settings = Settings.from_env(env)
    except Exception:  # noqa: BLE001 -- Preflight must redact every configuration exception to protect secrets.
        settings = None
    checks['api_configuration'] = settings is not None
    checks['email_provider'] = settings is not None and settings.email_auth is not None
    checks['auth_reset_mail_configuration'] = bool(settings and settings.email_auth
        and env.get('WORKER_QUEUE_DATABASE_URL'))
    origin = env.get('INROU_APP_ORIGIN', '').rstrip('/')
    try:
        parts = urlsplit(origin)
    except ValueError:
        parts = urlsplit('')
    checks['public_https_origin'] = bool(parts.scheme == 'https' and parts.hostname
        and not parts.username and not parts.password and not parts.path and not parts.query and not parts.fragment)
    checks['matching_email_origin'] = bool(settings and settings.email_auth
        and settings.email_auth.origin == origin)
    header = env.get('INROU_CLIENT_IP_HEADER', '')
    checks['signed_client_ip_configuration'] = bool(re.fullmatch(r'[a-z0-9-]{1,64}', header)
        and header not in ('forwarded', 'x-forwarded-for') and len(env.get('API_PROXY_HMAC_KEY', '')) >= 32)
    checks['direct_read_configuration'] = bool(settings and settings.oauth_direct and settings.token_keys)
    checks['worker_configuration'] = bool(env.get('WORKER_ENABLED') == '1'
        and env.get('WORKER_DATABASE_URL') and env.get('WORKER_QUEUE_DATABASE_URL')
        and re.fullmatch(r'[a-fA-F0-9]{40}', env.get('RELEASE_COMMIT_SHA', ''))
        and env.get('RELEASE_BUILD_ID'))
    checks['retention_configuration'] = bool(env.get('RETENTION_ENABLED') == '1'
        and env.get('RETENTION_DATABASE_URL'))
    for document in ('offer', 'pd_consent', 'privacy', 'cookies', 'requisites'):
        approved = False
        try:
            raw = text_path(document, VERSIONS[document][-1]).read_bytes()
            approved = bool(settings and 'ЗАГЛУШКА' not in raw.decode('utf-8')
                and hmac.compare_digest(settings.signup_approved_hashes.get(document, ''), hashlib.sha256(raw).hexdigest()))
        except (OSError, ValueError, KeyError):
            pass
        checks['approved_' + document] = approved
    return {'configuration_ready': all(checks.values()), 'checks': checks,
        'manual_checks_required': ['ingress_overwrites_spoofed_ip', 'email_delivery_and_reset',
            'two_client_tenant_isolation', 'direct_read_only_oauth_and_sync', 'backup_restore_and_retention'],
        'launch_approved': False}


def main():
    result = inspect(os.environ)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['configuration_ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
