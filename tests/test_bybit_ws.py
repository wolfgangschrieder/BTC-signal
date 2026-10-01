import asyncio
import time

import pytest

from research_os.exchanges.bybit.ws import BybitWebSocket, BybitWebSocketConfig


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
