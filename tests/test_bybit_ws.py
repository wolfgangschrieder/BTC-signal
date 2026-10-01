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
