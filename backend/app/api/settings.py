"""Настройки API — только из окружения (секреты в репозитории не хранятся). Строка подключения — роль app_rw:
API работает прикладной ролью под RLS; суперпользователь или роль с BYPASSRLS отвергаются при подключении (db.py)."""

import os
import json
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlsplit

from app.auth.login import SCOPES
from app.auth.yandex_oauth import OAuthApp
from app.auth.email_config import EmailAuthConfig

DEFAULT_MAX_BODY = 64 * 1024
SESSION_COOKIE = "session"


class SettingsError(ValueError):
    pass


def _origin(value: str) -> str:
    """Origin — схема://хост[:порт] без пути: ровно так его присылает браузер."""
    parts = urlsplit(value)
    if parts.scheme not in ("https", "http") or not parts.netloc or parts.path or parts.query or parts.fragment:
        raise SettingsError(f"API_ALLOWED_ORIGINS: не origin: {value!r}")
    return f"{parts.scheme}://{parts.netloc}".lower()


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)  # может содержать пароль — не в repr и не в логах
    allowed_origins: frozenset[str]
    hsts: bool = False
    max_body_bytes: int = DEFAULT_MAX_BODY
    session_cookie: str = SESSION_COOKIE
    pool_min_size: int = 1
    pool_max_size: int = 10
    pool_timeout: float = 5.0
    oauth_login: OAuthApp | None = field(default=None, repr=False)
    signup_approved_hashes: dict[str, str] = field(default_factory=dict, repr=False)
    email_auth: EmailAuthConfig | None = field(default=None, repr=False)

    def __post_init__(self):
        if not self.database_url:
            raise SettingsError("API_DATABASE_URL не задан")
        if not self.allowed_origins:
            raise SettingsError("API_ALLOWED_ORIGINS пуст: без списка изменяющие запросы принять нельзя")
        object.__setattr__(self, "allowed_origins", frozenset(_origin(o) for o in self.allowed_origins))
        if self.max_body_bytes <= 0:
            raise SettingsError("API_MAX_BODY_BYTES: нужно положительное число")
        if self.email_auth and self.email_auth.origin not in self.allowed_origins:
            raise SettingsError('REKVERO_EMAIL_ORIGIN must be an API_ALLOWED_ORIGINS member')
        if self.oauth_login:
            uri = urlsplit(self.oauth_login.redirect_uri)
            origin = f"{uri.scheme}://{uri.netloc}".lower()
            if (origin not in self.allowed_origins or uri.username or uri.password or uri.query or uri.fragment
                    or uri.path != "/api/auth/yandex/callback"
                    or (uri.scheme != "https" and uri.hostname not in ("localhost", "127.0.0.1", "::1"))):
                raise SettingsError("YANDEX_LOGIN_REDIRECT_URI: нужен доверенный callback сайта по HTTPS")

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        origins = frozenset(o.strip() for o in env.get("API_ALLOWED_ORIGINS", "").split(",") if o.strip())
        oauth = None
        if _flag(env.get("YANDEX_LOGIN_ENABLED")) and all(
                env.get(f"YANDEX_LOGIN_{key}") for key in ("CLIENT_ID", "CLIENT_SECRET", "REDIRECT_URI")):
            oauth = OAuthApp.from_env("YANDEX_LOGIN", SCOPES, env)
        try:
            approvals = json.loads(env.get("API_SIGNUP_APPROVED_HASHES", "{}"))
        except (ValueError, TypeError):
            raise SettingsError("API_SIGNUP_APPROVED_HASHES: нужен JSON объект хэшей документов") from None
        if not isinstance(approvals, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                                for k, v in approvals.items()):
            raise SettingsError("API_SIGNUP_APPROVED_HASHES: нужен JSON объект хэшей документов")
        return cls(
            database_url=env.get("API_DATABASE_URL", ""),
            allowed_origins=origins,
            hsts=_flag(env.get("API_HSTS")),
            max_body_bytes=int(env.get("API_MAX_BODY_BYTES", DEFAULT_MAX_BODY)),
            session_cookie=env.get("API_SESSION_COOKIE", SESSION_COOKIE),
            pool_min_size=int(env.get("API_POOL_MIN", 1)),
            pool_max_size=int(env.get("API_POOL_MAX", 10)),
            oauth_login=oauth,
            signup_approved_hashes=approvals,
            email_auth=EmailAuthConfig.from_env(env),
        )
