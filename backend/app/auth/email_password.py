"""Bounded scrypt hashes and canonical email identity, independent of Yandex ID."""
import hashlib
import hmac
import re
import secrets


def normalize_email(raw: str) -> str:
    raw = raw.strip()
    if len(raw) > 254 or raw.count('@') != 1 or any(c in raw for c in '\r\n\x00'):
        raise ValueError('invalid_email')
    local, domain = raw.rsplit('@', 1)
    try:
        domain = domain.encode('idna').decode('ascii').lower()
    except UnicodeError:
        raise ValueError('invalid_email') from None
    if (not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}", local)
            or local.startswith('.') or local.endswith('.') or '..' in local
            or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', domain)
            or '.' not in domain or any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-')
                                         for label in domain.split('.'))):
        raise ValueError('invalid_email')
    normalized = local.lower() + '@' + domain
    if len(normalized) > 254:
        raise ValueError('invalid_email')
    return normalized


def valid_password(password: str):
    if not 12 <= len(password) <= 128 or len(password.encode()) > 512 or '\x00' in password:
        raise ValueError('invalid_password')


def password_hash(password: str) -> str:
    valid_password(password)
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=3, maxmem=67108864, dklen=32)
    return 'scrypt$32768$8$3$' + salt.hex() + '$' + value.hex()


def password_matches(password: str, stored: str) -> bool:
    if len(password) > 128 or len(password.encode()) > 512:
        return False
    parts = stored.split('$')
    if len(parts) != 6 or parts[:4] != ['scrypt', '32768', '8', '3']:
        return False
    try:
        salt, expected = bytes.fromhex(parts[4]), bytes.fromhex(parts[5])
        if len(salt) != 16 or len(expected) != 32:
            return False
        actual = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=3, maxmem=67108864, dklen=32)
        return hmac.compare_digest(actual, expected)
    except (ValueError, OverflowError):
        return False


def token_hash(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


DUMMY_HASH = 'scrypt$32768$8$3$' + '00' * 16 + '$' + '00' * 32
