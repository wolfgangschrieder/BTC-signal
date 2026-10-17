from datetime import datetime, UTC, timedelta
from unittest.mock import AsyncMock
import pytest
from research_os.pipeline.candle_recovery import normalize_page, recover_history

NOW = datetime(2026, 10, 17, tzinfo=UTC)
def payload(when, close="101"):
    return {"result": {"symbol": "BTCUSDT", "category": "linear", "list": [
        [str(int(when.timestamp()*1000)), "100", "102", "99", close, "1", "100"]]}}

def test_only_closed_bars_and_actual_receipt_time():
    assert not normalize_page(payload(NOW), "BTCUSDT", NOW, NOW)
    event, = normalize_page(payload(NOW-timedelta(minutes=1)), "BTCUSDT", NOW, NOW)
    assert event.point_in_time_available_at == NOW
    assert event.ingestion_time == NOW
    assert event.event_time == NOW-timedelta(minutes=1)
    assert event.payload["confirm"] is True
    with pytest.raises(ValueError):
        normalize_page(payload(NOW-timedelta(minutes=1), "103"), "BTCUSDT", NOW, NOW)
    with pytest.raises(ValueError):
        normalize_page(payload(NOW), "OTHER", NOW, NOW)

@pytest.mark.asyncio
async def test_bounded_pagination_and_persistence():
    rest = AsyncMock()
    rest.get_kline.side_effect = [payload(NOW-timedelta(minutes=1)),
                                payload(NOW-timedelta(minutes=1001))]
    batches = []
    def persist(events):
        batches.extend(events)
        return len(events)
    assert await recover_history(rest, "BTCUSDT", NOW, 1001, persist) == 2
    assert rest.get_kline.await_count == 2
    calls = rest.get_kline.call_args_list
    assert calls[1].kwargs["end"] < calls[0].kwargs["end"]
    assert len(batches) == 2
