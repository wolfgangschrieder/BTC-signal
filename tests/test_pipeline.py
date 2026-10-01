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
