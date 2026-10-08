import pytest

from research_os.data.models import EventType, RawEvent
from research_os.data.pipeline import IngestionPipeline


@pytest.mark.asyncio
async def test_pipeline_applies_backpressure_limit():
    pipeline = IngestionPipeline(max_queue_size=1)
    event = RawEvent(
        source="test",
        event_type=EventType.TRADE,
        symbol="BTCUSDT",
        event_time=pipeline.now_utc(),
        ingestion_time=pipeline.now_utc(),
        point_in_time_available_at=pipeline.now_utc(),
        payload={"price": "1", "size": "1"},
    )
    await pipeline.publish(event)
    assert pipeline.queue.qsize() == 1


@pytest.mark.asyncio
async def test_writer_failure_unblocks_publish_and_drain():
    import asyncio

    pipeline = IngestionPipeline(max_queue_size=1)

    def fail(_event):
        raise RuntimeError("database unavailable")

    pipeline._persist_one = fail
    await pipeline.publish(object())
    writer = asyncio.create_task(pipeline.run_writer(asyncio.Event()))
    with pytest.raises(RuntimeError, match="database unavailable"):
        await writer
    for operation in (pipeline.publish(object()), pipeline.drain()):
        with pytest.raises(RuntimeError, match="ingestion writer failed"):
            await asyncio.wait_for(operation, timeout=1)


@pytest.mark.asyncio
async def test_publish_and_drain_waiters_wake_on_writer_failure():
    import asyncio
    from threading import Event

    entered, release = Event(), Event()
    pipeline = IngestionPipeline(max_queue_size=1)

    def fail(_event):
        entered.set()
        release.wait(2)
        raise RuntimeError("database unavailable")

    pipeline._persist_one = fail
    await pipeline.publish(object())
    writer = asyncio.create_task(pipeline.run_writer(asyncio.Event()))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        await pipeline.publish(object())
        publish = asyncio.create_task(pipeline.publish(object()))
        drain = asyncio.create_task(pipeline.drain())
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(RuntimeError, match="database unavailable"):
            await writer
        for task in (publish, drain):
            with pytest.raises(RuntimeError, match="ingestion writer failed"):
                await asyncio.wait_for(task, 1)
    finally:
        release.set()
        await asyncio.gather(writer, return_exceptions=True)
