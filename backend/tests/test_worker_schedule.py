"""Планировщик воркера: расписание по интервалам, изоляция сбоя одной задачи, остановка по событию, интервалы из env."""

import asyncio
import logging

import pytest

from app.worker.schedule import Job, ScheduleError, interval_from_env, run_jobs


def run(jobs, *, stop_after: float) -> None:
    async def main():
        stop = asyncio.Event()
        asyncio.get_running_loop().call_later(stop_after, stop.set)
        await asyncio.wait_for(run_jobs(jobs, stop), timeout=stop_after + 2)
    asyncio.run(main())


def test_jobs_run_at_start_and_repeat_by_interval():
    calls = {"fast": 0, "slow": 0}
    jobs = [Job("fast", 0.05, lambda: calls.__setitem__("fast", calls["fast"] + 1)),
            Job("slow", 10, lambda: calls.__setitem__("slow", calls["slow"] + 1))]
    run(jobs, stop_after=0.3)
    assert calls["slow"] == 1          # сразу при старте, следующий запуск — через 10 с
    assert 3 <= calls["fast"] <= 8     # ~0.3 / 0.05, с запасом на медленную машину


def test_failing_job_does_not_stop_others(caplog):
    calls = []

    def broken():
        raise RuntimeError("boom")

    jobs = [Job("broken", 0.05, broken), Job("ok", 0.05, lambda: calls.append(1))]
    with caplog.at_level(logging.ERROR, logger="ai_direct.worker"):
        run(jobs, stop_after=0.25)
    assert len(calls) >= 3
    failures = [r for r in caplog.records if getattr(r, "job", None) == "broken"]
    assert failures and failures[0].exc_info  # сбой записан с трассировкой, цикл продолжился


def test_stop_ends_loop_without_waiting_for_long_interval():
    async def main():
        stop = asyncio.Event()
        task = asyncio.create_task(run_jobs([Job("daily", 86400, lambda: None)], stop))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=1)  # не ждёт суток до следующего запуска
    asyncio.run(main())


def test_running_job_finishes_before_stop():
    finished = []

    def slow():
        import time
        time.sleep(0.2)
        finished.append(1)

    async def main():
        stop = asyncio.Event()
        task = asyncio.create_task(run_jobs([Job("slow", 60, slow)], stop))
        await asyncio.sleep(0.05)
        stop.set()  # задача уже идёт: остановка дожидается её, а не обрывает посередине
        await asyncio.wait_for(task, timeout=2)
    asyncio.run(main())
    assert finished == [1]


@pytest.mark.parametrize("env, expected", [({}, 60), ({"WORKER_NOTIFY_EVERY": "15"}, 15)])
def test_interval_from_env(env, expected):
    assert interval_from_env("notify", 60, env) == expected


@pytest.mark.parametrize("value", ["", "0", "-5", "abc", "1.5"])
def test_interval_from_env_rejects_garbage(value):
    with pytest.raises(ScheduleError, match="WORKER_NOTIFY_EVERY"):
        interval_from_env("notify", 60, {"WORKER_NOTIFY_EVERY": value})
