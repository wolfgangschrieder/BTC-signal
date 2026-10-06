import asyncio

import pytest

from research_os.pipeline.live import LiveSignalService


@pytest.mark.asyncio
async def test_event_publisher_failure_keeps_persistence_unhealthy():
    async def failing_publisher(_event):
        raise RuntimeError("database unavailable")

    service = LiveSignalService(publisher=failing_publisher)
    task = asyncio.create_task(service._cold_event_publisher())
    service._event_publish_queue.put_nowait(object())
    await service._event_publish_queue.join()
    assert service._event_persistence_healthy is False
    await service._event_publish_queue.put(service._writer_stop)
    await task


@pytest.mark.asyncio
async def test_outcome_publisher_failure_marks_outcome_persistence_unhealthy():
    service = LiveSignalService()
    task = asyncio.create_task(service._cold_outcome_writer())
    service._outcome_write_queue.put_nowait(object())
    await service._outcome_write_queue.join()
    # The malformed sentinel-like object is rejected by the writer and must
    # fail closed rather than silently claiming persistence is healthy.
    assert service._outcome_persistence_healthy is False
    await service._outcome_write_queue.put(service._writer_stop)
    await task


@pytest.mark.asyncio
async def test_notification_failure_is_observable_without_killing_writer():
    class FailingTelegram:
        async def send(self, _text):
            raise RuntimeError("telegram unavailable")

    service = LiveSignalService(telegram=FailingTelegram())
    task = asyncio.create_task(service._cold_notification_writer())
    service._notification_queue.put_nowait("signal")
    await service._notification_queue.join()
    assert service._notification_healthy is False
    await service._notification_queue.put(service._writer_stop)
    await task


@pytest.mark.asyncio
async def test_state_writer_failure_marks_state_persistence_unhealthy():
    service = LiveSignalService()
    task = asyncio.create_task(service._cold_writer())
    service._state_write_queue.put_nowait(object())
    await service._state_write_queue.join()
    assert service._state_persistence_healthy is False
    await service._state_write_queue.put(service._writer_stop)
    await task
