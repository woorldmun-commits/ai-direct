"""Explicit SMTP configuration; no production console-mail fallback."""
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import parseaddr
import smtplib
import ssl
import httpx
from urllib.parse import urlsplit


@dataclass(frozen=True)
class EmailAuthConfig:
    origin: str
    hmac_key: str = field(repr=False)
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_user: str = ''
    smtp_password: str = field(default='', repr=False)
    smtp_from: str = ''
    provider: str = 'smtp'
    api_key: str = field(default='', repr=False)

    def __post_init__(self):
        u = urlsplit(self.origin)
        if (u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password
                or u.path or u.query or u.fragment
                or (u.scheme != 'https' and u.hostname not in ('127.0.0.1', 'localhost', '::1'))):
            raise ValueError('Email origin must be a trusted HTTPS origin')
        if (len(self.hmac_key.encode()) < 32 or self.provider not in ('smtp', 'unisender')
                or (self.provider == 'smtp' and (not self.smtp_host or not 1 <= self.smtp_port <= 65535))
                or (self.provider == 'unisender' and not self.api_key.strip())):
            raise ValueError('Incomplete email configuration')
        if any(c in self.smtp_from for c in '\r\n') or parseaddr(self.smtp_from)[1] != self.smtp_from or '@' not in self.smtp_from:
            raise ValueError('Invalid sender address')
        if bool(self.smtp_user) != bool(self.smtp_password):
            raise ValueError('SMTP user and password must be configured together')

    @classmethod
    def from_env(cls, env):
        if env.get('INROU_EMAIL_ENABLED', '').lower() not in ('1', 'true', 'yes'):
            return None
        return cls(env.get('INROU_EMAIL_ORIGIN', ''), env.get('INROU_AUTH_HMAC_KEY', ''),
                   env.get('INROU_SMTP_HOST', ''), int(env.get('INROU_SMTP_PORT', '587')),
                   env.get('INROU_SMTP_USER', ''), env.get('INROU_SMTP_PASSWORD', ''),
                   env.get('INROU_SMTP_FROM', ''), env.get('INROU_MAIL_PROVIDER', 'smtp'),
                   env.get('INROU_MAIL_API_KEY', ''))


def send(config: EmailAuthConfig, recipient: str, purpose: str, url: str):
    message = EmailMessage()
    message['From'], message['To'] = config.smtp_from, recipient
    message['Subject'] = 'inrou: подтверждение почты' if purpose == 'verify' else 'inrou: восстановление пароля'
    message.set_content(('Подтвердите email и повторно введите выбранный пароль: ' if purpose == 'verify'
                         else 'Установите новый пароль: ') + url + '\nЕсли вы не запрашивали это письмо, ничего не делайте.')
    _deliver(config, recipient, message)


def send_message(config: EmailAuthConfig, recipient: str, subject: str, text: str, message_id: str):
    if (len(recipient) > 254 or any(c in recipient for c in '\r\n')
            or parseaddr(recipient)[1] != recipient or '@' not in recipient):
        raise ValueError('Invalid recipient')
    message = EmailMessage()
    message['From'], message['To'] = config.smtp_from, recipient
    message['Subject'], message['Message-ID'] = subject, message_id
    message.set_content(text)
    _deliver(config, recipient, message)


def _deliver(config, recipient, message):
    if config.provider == 'unisender':
        # A fixed Russian API endpoint avoids SMTP blocks and cannot redirect credentials.
        try:
            with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
                response = client.post('https://goapi.unisender.ru/ru/transactional/api/v1/email/send.json',
                    headers={'X-API-KEY': config.api_key}, json={'message': {
                        'recipients': [{'email': recipient}], 'from_email': config.smtp_from,
                        'from_name': 'inrou', 'subject': str(message['Subject']),
                        'body': {'plaintext': message.get_content()}, 'track_links': 0, 'track_read': 0}})
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict) or result.get('status') != 'success':
                    raise ValueError('Mail delivery unavailable')
        except Exception:
            raise RuntimeError('Mail delivery unavailable') from None
        return
    context = ssl.create_default_context()
    if config.smtp_port == 465:
        client = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=10, context=context)
    else:
        client = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10)
    with client:
        if config.smtp_port != 465:
            client.starttls(context=context)
        if config.smtp_user:
            client.login(config.smtp_user, config.smtp_password)
        client.send_message(message)
