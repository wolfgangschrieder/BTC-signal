import asyncio

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
