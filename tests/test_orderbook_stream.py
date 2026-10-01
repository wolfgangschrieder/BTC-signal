import pytest

from research_os.data.models import QualityCode
from research_os.exchanges.bybit.orderbook_stream import BybitOrderBookStream
from research_os.exchanges.bybit.ws import BybitReconnectRequired


@pytest.mark.asyncio
async def test_sequence_failure_requests_reconnect():
    stream = BybitOrderBookStream("BTCUSDT")
    await stream._handle_message({
        "topic": "orderbook.50.BTCUSDT",
        "type": "snapshot",
        "ts": 1000,
        "data": {
            "u": 10, "seq": 100,
            "b": [["100", "1"]], "a": [["101", "1"]],
        },
    })
    with pytest.raises(BybitReconnectRequired):
        await stream._handle_message({
            "topic": "orderbook.50.BTCUSDT",
            "type": "delta",
            "ts": 1100,
            "data": {"u": 11, "seq": 99, "b": [], "a": []},
        })
    assert stream.state.valid is False


@pytest.mark.asyncio
async def test_quality_handler_receives_gap():
    events = []

    async def collect(event):
        events.append(event)

    stream = BybitOrderBookStream("BTCUSDT", quality_handler=collect)
    with pytest.raises(BybitReconnectRequired):
        await stream._handle_message({
            "topic": "orderbook.50.BTCUSDT",
            "type": "delta",
            "ts": 1100,
            "data": {},
        })
    assert events[0].code == QualityCode.ORDERBOOK_GAP
