import asyncio
from threading import Event

import pytest

from research_os.pipeline.outcome_scheduler import OutcomeResolutionScheduler


@pytest.mark.asyncio
async def test_resolution_runs_immediately_and_stop_interrupts_interval(monkeypatch):
    stop = asyncio.Event()
    resolved = Event()
    scheduler = OutcomeResolutionScheduler(interval_seconds=3600)
    monkeypatch.setattr(scheduler, "_resolve", lambda: resolved.set())
    task = asyncio.create_task(scheduler.run(stop))
    assert await asyncio.to_thread(resolved.wait, 1)
    stop.set()
    await asyncio.wait_for(task, 1)


@pytest.mark.asyncio
async def test_database_failure_is_retried_without_stopping_scheduler(monkeypatch, caplog):
    stop = asyncio.Event()
    resolved = Event()
    attempts = []
    scheduler = OutcomeResolutionScheduler(interval_seconds=0.01)

    def resolve():
        attempts.append(True)
        if len(attempts) == 1:
            raise RuntimeError("database unavailable")
        resolved.set()

    monkeypatch.setattr(scheduler, "_resolve", resolve)
    task = asyncio.create_task(scheduler.run(stop))
    try:
        assert await asyncio.to_thread(resolved.wait, 1)
        assert len(attempts) >= 2
        assert "Outcome resolution failed (RuntimeError)" in caplog.text
    finally:
        stop.set()
        await asyncio.wait_for(task, 1)


@pytest.mark.asyncio
async def test_resolution_does_not_block_event_loop(monkeypatch):
    stop = asyncio.Event()
    entered, release = Event(), Event()
    scheduler = OutcomeResolutionScheduler()

    def slow_resolve():
        entered.set()
        release.wait(2)

    monkeypatch.setattr(scheduler, "_resolve", slow_resolve)
    task = asyncio.create_task(scheduler.run(stop))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        await asyncio.wait_for(asyncio.sleep(0.01), 0.5)
    finally:
        release.set()
        stop.set()
        await asyncio.wait_for(task, 1)
