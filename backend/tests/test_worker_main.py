"""Точка запуска воркера: конфигурация из окружения, версия кода, каждая задача — под своей ролью БД."""

import pytest

from app.worker.main import build_jobs, measure, notify, release_id, retention
from app.worker.schedule import ScheduleError
from test_api_support import dsn

SHA = "c" * 40


@pytest.fixture
def env(db):
    return {"WORKER_DATABASE_URL": dsn(db, "app_token"), "WORKER_SYSTEM_DATABASE_URL": dsn(db, "app_system"),
            "WORKER_DELETER_DATABASE_URL": dsn(db, "app_deleter"), "RELEASE_COMMIT_SHA": SHA,
            "RELEASE_BUILD_ID": "worker-test"}


def test_build_jobs_with_intervals(env):
    jobs = build_jobs({**env, "WORKER_NOTIFY_EVERY": "5"})
    assert [(j.name, j.every) for j in jobs] == [("notify", 5), ("measure", 3600), ("retention", 86400)]


@pytest.mark.parametrize("missing", ["WORKER_DATABASE_URL", "WORKER_SYSTEM_DATABASE_URL",
                                     "WORKER_DELETER_DATABASE_URL", "RELEASE_COMMIT_SHA", "RELEASE_BUILD_ID"])
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
