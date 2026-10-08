import pytest

from research_os.pipeline.live import LiveSignalService


def batch():
    item = {"s": "BTCUSDT", "p": "100", "v": "1", "T": 1767225600000}
    return {
        "topic": "publicTrade.BTCUSDT",
        "data": [{**item, "S": "Buy", "i": "one"}, {**item, "S": "Sell", "i": "two"}],
    }


@pytest.mark.asyncio
async def test_live_batch_updates_flow_and_queues_every_trade():
    async def publish(event):
        pass

    service = LiveSignalService(publisher=publish)
    await service._handle(batch())
    assert len(service.trades) == 2
    assert service.cumulative_delta == 0
    assert service._event_publish_queue.qsize() == 2
    assert [service._event_publish_queue.get_nowait().payload["trade_id"] for _ in range(2)] == [
        "one",
        "two",
    ]
    assert service.trade_normalization_errors == 0


@pytest.mark.asyncio
async def test_invalid_batch_does_not_apply_partial_flow_and_disables_signals(caplog):
    service = LiveSignalService()
    message = batch()
    message["data"][1]["v"] = "-1"
    await service._handle(message)
    assert not service.trades
    assert service.cumulative_delta == 0
    assert service.trade_normalization_errors == 1
    assert not service._trade_data_healthy
    assert "Rejected Bybit trade batch" in caplog.text
    await service._handle(batch())
    assert len(service.trades) == 2
    assert not service._trade_data_healthy


@pytest.mark.asyncio
async def test_wrong_symbol_batch_is_rejected():
    service = LiveSignalService()
    message = batch()
    message["data"][1]["s"] = "ETHUSDT"
    await service._handle(message)
    assert not service.trades
    assert not service._trade_data_healthy
