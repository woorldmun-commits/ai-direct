"""HTTP API (FastAPI): граница запроса, сессия → actor, вход в workspace под RLS. Только чтение в v1.0-фундаменте."""

from app.api.app import create_app

__all__ = ["create_app"]
