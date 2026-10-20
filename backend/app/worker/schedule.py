"""Планировщик воркера: asyncio-цикл по интервалам, без очереди и внешних зависимостей.

Задачи выполняются по одной в отдельном потоке (функции задач синхронные, psycopg): медленная задача задерживает
остальные, но две задачи не делят соединения и не гоняются за одними строками. Исключение задачи пишется в лог,
следующий запуск — по расписанию: сбой одной задачи не останавливает остальные. Остановка (stop) не обрывает
задачу посередине — цикл дожидается её и выходит.
ponytail: интервалы, а не время суток (06:00 МСК, ARCHITECTURE.md §2.6) и один процесс; cron и очередь — когда
появятся синхронизации по расписанию и второй воркер."""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from app.obs.log import bind

log = logging.getLogger("ai_direct.worker")


class ScheduleError(ValueError):
    pass


@dataclass(frozen=True)
class Job:
    name: str
    every: float  # секунды между окончанием запуска и началом следующего
    run: Callable[[], object]


def interval_from_env(name: str, default: int, env: Mapping[str, str]) -> int:
    """WORKER_<NAME>_EVERY — целое число секунд > 0; не задано — default."""
    key = f"WORKER_{name.upper()}_EVERY"
    raw = env.get(key)
    if raw is None:
        return default
    if not raw.strip().isdigit() or int(raw) <= 0:
        raise ScheduleError(f"{key}: нужно целое число секунд > 0")
    return int(raw)


async def _run_one(job: Job) -> None:
    started = time.monotonic()
    with bind(job=job.name):
        try:
            result = await asyncio.to_thread(job.run)
        except Exception:
            log.exception("job failed", extra={"job": job.name,
                                               "duration_ms": round((time.monotonic() - started) * 1000)})
            return
        log.info("job done", extra={"job": job.name, "result": result if isinstance(result, int) else None,
                                    "duration_ms": round((time.monotonic() - started) * 1000)})


async def run_jobs(jobs: Iterable[Job], stop: asyncio.Event) -> None:
    jobs = list(jobs)
    if not jobs:
        await stop.wait()
        return
    next_at = {job.name: time.monotonic() for job in jobs}  # все задачи — сразу при старте
    while not stop.is_set():
        for job in jobs:
            if stop.is_set():
                break
            if next_at[job.name] <= time.monotonic():
                await _run_one(job)
                next_at[job.name] = time.monotonic() + job.every
        delay = max(0.0, min(next_at.values()) - time.monotonic())
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
        except TimeoutError:
            pass
