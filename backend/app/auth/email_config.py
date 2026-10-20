"""Explicit SMTP configuration; no production console-mail fallback."""
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import parseaddr
import smtplib
import ssl
from urllib.parse import urlsplit


@dataclass(frozen=True)
class EmailAuthConfig:
    origin: str
    hmac_key: str = field(repr=False)
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str = ''
    smtp_password: str = field(default='', repr=False)
    smtp_from: str = ''

    def __post_init__(self):
        u = urlsplit(self.origin)
        if (u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password
                or u.path or u.query or u.fragment
                or (u.scheme != 'https' and u.hostname not in ('127.0.0.1', 'localhost', '::1'))):
            raise ValueError('Email origin must be a trusted HTTPS origin')
        if len(self.hmac_key.encode()) < 32 or not self.smtp_host or not 1 <= self.smtp_port <= 65535:
            raise ValueError('Incomplete email configuration')
        if any(c in self.smtp_from for c in '\r\n') or parseaddr(self.smtp_from)[1] != self.smtp_from or '@' not in self.smtp_from:
            raise ValueError('Invalid sender address')
        if bool(self.smtp_user) != bool(self.smtp_password):
            raise ValueError('SMTP user and password must be configured together')

    @classmethod
    def from_env(cls, env):
        if env.get('REKVERO_EMAIL_ENABLED', '').lower() not in ('1', 'true', 'yes'):
            return None
        return cls(env.get('REKVERO_EMAIL_ORIGIN', ''), env.get('REKVERO_AUTH_HMAC_KEY', ''),
                   env.get('REKVERO_SMTP_HOST', ''), int(env.get('REKVERO_SMTP_PORT', '587')),
                   env.get('REKVERO_SMTP_USER', ''), env.get('REKVERO_SMTP_PASSWORD', ''),
                   env.get('REKVERO_SMTP_FROM', ''))


def send(config: EmailAuthConfig, recipient: str, purpose: str, url: str):
    message = EmailMessage()
    message['From'], message['To'] = config.smtp_from, recipient
    message['Subject'] = 'Rekvero: подтверждение почты' if purpose == 'verify' else 'Rekvero: восстановление пароля'
    message.set_content(('Подтвердите email и повторно введите выбранный пароль: ' if purpose == 'verify'
                         else 'Установите новый пароль: ') + url + '\nЕсли вы не запрашивали это письмо, ничего не делайте.')
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
