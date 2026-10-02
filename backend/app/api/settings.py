"""Настройки API — только из окружения (секреты в репозитории не хранятся). Строка подключения — роль app_rw:
API работает прикладной ролью под RLS; суперпользователь или роль с BYPASSRLS отвергаются при подключении (db.py)."""

import os
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlsplit

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

    def __post_init__(self):
        if not self.database_url:
            raise SettingsError("API_DATABASE_URL не задан")
        if not self.allowed_origins:
            raise SettingsError("API_ALLOWED_ORIGINS пуст: без списка изменяющие запросы принять нельзя")
        object.__setattr__(self, "allowed_origins", frozenset(_origin(o) for o in self.allowed_origins))
        if self.max_body_bytes <= 0:
            raise SettingsError("API_MAX_BODY_BYTES: нужно положительное число")

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        origins = frozenset(o.strip() for o in env.get("API_ALLOWED_ORIGINS", "").split(",") if o.strip())
        return cls(
            database_url=env.get("API_DATABASE_URL", ""),
            allowed_origins=origins,
            hsts=_flag(env.get("API_HSTS")),
            max_body_bytes=int(env.get("API_MAX_BODY_BYTES", DEFAULT_MAX_BODY)),
            session_cookie=env.get("API_SESSION_COOKIE", SESSION_COOKIE),
            pool_min_size=int(env.get("API_POOL_MIN", 1)),
            pool_max_size=int(env.get("API_POOL_MAX", 10)),
        )
