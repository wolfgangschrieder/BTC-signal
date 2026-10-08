import asyncio

import httpx
import pytest

from research_os.pipeline.live import LiveSignalService


def restore(service, timestamp=1000):
    service.orderbook.restore_snapshot([["100", "1"]], [["101", "1"]], 1, 1, timestamp)


def test_disconnect_invalidates_book_and_discontinuous_history():
    service = LiveSignalService()
    restore(service)
    service.closes.extend([100, 101, 102])
    service.cumulative_delta = 10
    service._ofi_history.append((1000, 1))
    service._reset_stream_state()
    assert not service.orderbook.state.valid
    assert not service.closes
    assert not service._ofi_history
    assert service.cumulative_delta == 0


@pytest.mark.asyncio
async def test_recovery_handles_network_failure_then_restores(monkeypatch):
    service = LiveSignalService()

    async def failed(**kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(service.rest, "get_orderbook", failed)
    await service._recover_orderbook()
    assert not service.orderbook.state.valid

    async def restored(**kwargs):
        return {
            "time": 2000,
            "result": {"b": [["100", "1"]], "a": [["101", "1"]], "u": 2, "seq": 2},
        }

    monkeypatch.setattr(service.rest, "get_orderbook", restored)
    await service._recover_orderbook()
    assert service.orderbook.state.valid
    assert service.orderbook.state.update_id == 2


@pytest.mark.asyncio
async def test_rest_snapshot_cannot_overwrite_newer_websocket_snapshot(monkeypatch):
    service = LiveSignalService()

    async def restored(**kwargs):
        restore(service, timestamp=3000)
        return {"time": 2000, "result": {"b": [["99", "1"]], "a": [["102", "1"]], "u": 2}}

    monkeypatch.setattr(service.rest, "get_orderbook", restored)
    await service._recover_orderbook()
    assert service.orderbook.state.last_event_time_ms == 3000
    assert str(service.orderbook.state.bids[0].price) == "100"


@pytest.mark.asyncio
async def test_cancelled_service_cleans_up_blocked_publisher(monkeypatch):
    blocked = asyncio.Event()
    cancelled = asyncio.Event()

    async def publisher(event):
        blocked.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    service = LiveSignalService(publisher=publisher)

    async def bootstrap():
        service._enqueue_event(object())

    async def no_op():
        pass

    async def websocket():
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "_restore_cooldown", lambda: None)
    monkeypatch.setattr(service, "bootstrap_derivatives_history", bootstrap)
    monkeypatch.setattr(service, "bootstrap_orderbook", no_op)
    monkeypatch.setattr(service.websocket, "run", websocket)
    task = asyncio.create_task(service.run())
    await blocked.wait()
    # First cancellation enters graceful drain; second interrupts the blocked drain.
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 0.5)
    assert cancelled.is_set()
