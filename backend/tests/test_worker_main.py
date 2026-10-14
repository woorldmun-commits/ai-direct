"""Точка запуска воркера: конфигурация из окружения, версия кода, каждая задача — под своей ролью БД."""

import base64
from datetime import datetime, timezone

import psycopg
import pytest

from app.worker.main import build_jobs, measure, notify, release_id, retention
from app.worker.pipeline import run_pipeline
from app.worker.schedule import ScheduleError
from test_api_support import dsn

SHA = "c" * 40


@pytest.fixture
def env(db):
    return {"WORKER_DATABASE_URL": dsn(db, "app_token"), "WORKER_SYSTEM_DATABASE_URL": dsn(db, "app_system"),
            "WORKER_DELETER_DATABASE_URL": dsn(db, "app_deleter"), "RELEASE_COMMIT_SHA": SHA,
            "RELEASE_BUILD_ID": "worker-test", "YANDEX_API_CLIENT_ID": "id", "YANDEX_API_CLIENT_SECRET": "secret",
            "YANDEX_API_REDIRECT_URI": "https://example.test/cb", "TOKEN_ENCRYPTION_KEY_VERSION": "1",
            "TOKEN_ENCRYPTION_KEY_1": base64.b64encode(b"k" * 32).decode()}


def test_build_jobs_with_intervals(env):
    jobs = build_jobs({**env, "WORKER_NOTIFY_EVERY": "5"})
    assert [(j.name, j.every) for j in jobs] == [("notify", 5), ("pipeline", 60), ("measure", 3600),
                                                     ("retention", 86400)]


@pytest.mark.parametrize("missing", ["WORKER_DATABASE_URL", "WORKER_SYSTEM_DATABASE_URL",
                                     "WORKER_DELETER_DATABASE_URL", "RELEASE_COMMIT_SHA", "RELEASE_BUILD_ID",
                                     "YANDEX_API_CLIENT_SECRET", "TOKEN_ENCRYPTION_KEY_1"])
def test_build_jobs_requires_config(env, missing):
    with pytest.raises(ScheduleError):
        build_jobs({k: v for k, v in env.items() if k != missing})


def test_release_id_is_idempotent(env):
    first = release_id(env["WORKER_DATABASE_URL"], env)
    assert release_id(env["WORKER_DATABASE_URL"], env) == first


def test_jobs_run_under_their_roles(env):
    # права ролей достаточны для каждой задачи: проход по пустой (или чужой тестовой) очереди без ошибок
    assert notify(env["WORKER_SYSTEM_DATABASE_URL"]) >= 0
    assert measure(env["WORKER_SYSTEM_DATABASE_URL"], env["WORKER_DATABASE_URL"],
                   release_id(env["WORKER_DATABASE_URL"], env)) >= 0
    assert retention(env["WORKER_DELETER_DATABASE_URL"]) >= 0


def test_pipeline_runs_under_its_roles(env):
    """Постановка и захват — app_system, синхронизация и аудит — app_token. Источники-заглушки: без HTTP."""
    def no_api(sync_run_id):
        raise RuntimeError("no api in tests")
    release = release_id(env["WORKER_DATABASE_URL"], env)
    with psycopg.connect(env["WORKER_SYSTEM_DATABASE_URL"], autocommit=True) as system,             psycopg.connect(env["WORKER_DATABASE_URL"], autocommit=True) as token:
        assert run_pipeline(system, token, no_api, release_id=release, now=datetime.now(timezone.utc)) >= 0
