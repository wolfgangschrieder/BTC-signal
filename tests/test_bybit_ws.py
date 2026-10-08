import asyncio
import time

import pytest

from research_os.exchanges.bybit.ws import BybitWebSocket, BybitWebSocketConfig
from research_os.pipeline.latency import LatencyTelemetry


@pytest.mark.asyncio
async def test_malformed_message_does_not_reach_handler():
    received: list[dict] = []

    async def handler(message: dict) -> None:
        received.append(message)

    ws = BybitWebSocket(["orderbook.50.BTCUSDT"], handler)
    await ws._handle_message("{not-json")
    assert received == []


@pytest.mark.asyncio
async def test_handler_error_is_isolated():
    calls = 0

    async def handler(message: dict) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")

    ws = BybitWebSocket(["orderbook.50.BTCUSDT"], handler)
    await ws._handle_message('{"topic":"orderbook.50.BTCUSDT","type":"snapshot","data":{}}')
    await ws._handle_message('{"topic":"orderbook.50.BTCUSDT","type":"snapshot","data":{}}')
    assert calls == 2


@pytest.mark.asyncio
async def test_pong_records_application_latency():
    async def handler(message: dict) -> None:
        pass

    ws = BybitWebSocket(["orderbook.50.BTCUSDT"], handler)
    ws._ping_sent_monotonic = time.monotonic() - 0.02
    await ws._handle_message('{"op":"pong"}')
    assert ws.latency_ms is not None
    assert ws.latency_ms >= 0
    assert ws.latency_at is not None


@pytest.mark.asyncio
async def test_handler_load_telemetry_is_recorded():
    async def handler(message: dict) -> None:
        await asyncio.sleep(0)

    ws = BybitWebSocket(["orderbook.50.BTCUSDT"], handler)
    await ws._handle_message('{"topic":"orderbook.50.BTCUSDT","type":"snapshot","data":{}}')
    assert ws.messages_processed == 1
    assert ws.handler_errors == 0
    assert ws.last_handler_duration_ms is not None
    assert ws.last_handler_duration_ms >= 0
    assert ws.max_handler_duration_ms >= ws.last_handler_duration_ms


@pytest.mark.asyncio
async def test_transport_latency_telemetry_records_receive_decode_and_handler_stages():
    telemetry = LatencyTelemetry()

    async def handler(message: dict) -> None:
        pass

    ws = BybitWebSocket(["orderbook.50.BTCUSDT"], handler, latency=telemetry)
    await ws._handle_message('{"topic":"orderbook.50.BTCUSDT","type":"snapshot","data":{}}')
    report = telemetry.report()
    assert report["ws_decode"]["count"] == 1
    assert report["ws_handler"]["count"] == 1
    assert report["ws_decode"]["p99_ms"] is not None
    assert report["ws_handler"]["p99_ms"] is not None


@pytest.mark.asyncio
async def test_bybit_ping_reply_records_latency():
    async def handler(message):
        raise AssertionError("control messages must not reach handler")

    ws = BybitWebSocket(["test"], handler)
    ws._ping_sent_monotonic = time.monotonic() - 0.01
    await ws._handle_message('{"op":"ping","success":true,"ret_msg":"pong"}')
    assert ws.latency_ms is not None
    assert ws._pong.is_set()


@pytest.mark.asyncio
async def test_subscription_rejection_requests_reconnect():
    from research_os.exchanges.bybit.ws import BybitReconnectRequired

    async def handler(message):
        pass

    ws = BybitWebSocket(["test"], handler)
    with pytest.raises(BybitReconnectRequired):
        await ws._handle_message('{"op":"subscribe","success":false}')


@pytest.mark.asyncio
async def test_stop_interrupts_reconnect_backoff(monkeypatch):
    attempted = asyncio.Event()
    disconnected = []

    async def handler(message):
        pass

    ws = BybitWebSocket(
        ["test"],
        handler,
        BybitWebSocketConfig(reconnect_initial_seconds=30),
        on_disconnect=lambda: disconnected.append(True),
    )

    async def fail():
        attempted.set()
        raise ConnectionError("offline")

    monkeypatch.setattr(ws, "_run_connection", fail)
    task = asyncio.create_task(ws.run())
    await attempted.wait()
    await ws.stop()
    await asyncio.wait_for(task, 0.5)
    assert disconnected == [True]


@pytest.mark.asyncio
async def test_missing_application_pong_fails_connection():
    async def handler(message):
        pass

    class Socket:
        async def send(self, message):
            pass

    ws = BybitWebSocket(
        ["test"],
        handler,
        BybitWebSocketConfig(ping_interval_seconds=0.001, ping_timeout_seconds=0.01),
    )
    with pytest.raises(ConnectionError, match="pong timeout"):
        await asyncio.wait_for(ws._application_ping_loop(Socket()), 0.5)


@pytest.mark.asyncio
async def test_stop_closes_active_socket():
    async def handler(message):
        pass

    class Socket:
        closed = False

        async def close(self):
            self.closed = True

    ws = BybitWebSocket(["test"], handler)
    socket = Socket()
    ws._connection = socket
    await ws.stop()
    assert socket.closed


@pytest.mark.asyncio
async def test_real_local_transport_receives_data_and_stops_promptly():
    import json

    from websockets.asyncio.server import serve

    received = asyncio.Event()

    async def server(socket):
        subscription = json.loads(await socket.recv())
        assert subscription["op"] == "subscribe"
        await socket.send('{"topic":"test","data":[]}')
        await socket.wait_closed()

    async def handler(message):
        received.set()

    async with serve(server, "127.0.0.1", 0) as listener:
        port = listener.sockets[0].getsockname()[1]
        ws = BybitWebSocket(["test"], handler, BybitWebSocketConfig(url=f"ws://127.0.0.1:{port}"))
        task = asyncio.create_task(ws.run())
        try:
            await asyncio.wait_for(received.wait(), 1)
            await ws.stop()
            await asyncio.wait_for(task, 1)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert ws._connection is None


@pytest.mark.asyncio
async def test_real_local_transport_closes_when_server_does_not_pong():
    from websockets.asyncio.server import serve

    async def server(socket):
        await socket.recv()  # Subscription.
        await socket.recv()  # Application ping, intentionally not answered.
        await socket.wait_closed()

    async def handler(message):
        pass

    async with serve(server, "127.0.0.1", 0) as listener:
        port = listener.sockets[0].getsockname()[1]
        ws = BybitWebSocket(
            ["test"],
            handler,
            BybitWebSocketConfig(
                url=f"ws://127.0.0.1:{port}",
                ping_interval_seconds=0.01,
                ping_timeout_seconds=0.02,
            ),
        )
        with pytest.raises(ConnectionError, match="pong timeout"):
            await asyncio.wait_for(ws._run_connection(), 1)
        assert ws._connection is None
