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
