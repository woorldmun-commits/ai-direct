"""Эндпоинт мониторинга: GET /ops/health — свежесть синхронизаций и счётчики sync_run по статусам (obs/health.py).

Доступ — по токену мониторинга (Authorization: Bearer $OPS_TOKEN); токен не задан или не совпал — 404, как у
несуществующего пути. Ответ — только числа, статусы и время, без workspace и названий. Синхронизация не отработала
дольше OPS_SYNC_STALE_HOURS — 503: внешний мониторинг алертит по коду ответа.

Пул API работает ролью app_rw под RLS и чужих workspace не видит; сводка по всем — отдельное короткое соединение
системной роли (OPS_DATABASE_URL, app_system)."""

import hmac
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.errors import not_found
from app.obs.health import sync_health

router = APIRouter()
DEFAULT_STALE_HOURS = 26  # основная синхронизация раз в сутки (06:00 МСК) + 2 часа на её выполнение


def _authorized(request: Request, token: str) -> bool:
    sent = request.headers.get("authorization", "")
    return bool(token) and hmac.compare_digest(sent.encode(), f"Bearer {token}".encode())


@router.get("/ops/health")
def ops_health(request: Request):
    if not _authorized(request, os.environ.get("OPS_TOKEN", "")):
        raise not_found()
    stale_after = timedelta(hours=float(os.environ.get("OPS_SYNC_STALE_HOURS", DEFAULT_STALE_HOURS)))
    try:
        with psycopg.connect(os.environ["OPS_DATABASE_URL"], connect_timeout=3, autocommit=True) as conn:
            health = sync_health(conn, now=datetime.now(timezone.utc), stale_after=stale_after)
    except (KeyError, psycopg.Error):
        return JSONResponse({"status": "unavailable"}, status_code=503)
    body = asdict(health)
    body["last_success_at"] = health.last_success_at.isoformat() if health.last_success_at else None
    return JSONResponse(body, status_code=503 if health.status == "stale" else 200)
