from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from research_os.data.models import QualityEvent
from research_os.exchanges.bybit.orderbook import OrderBook, OrderBookState
from research_os.exchanges.bybit.ws import BybitReconnectRequired, BybitWebSocket, BybitWebSocketConfig

QualityHandler = Callable[[QualityEvent], Awaitable[None]]


class BybitOrderBookStream:
    """Connects the Bybit transport to a validated in-memory order book."""

    def __init__(
        self,
        symbol: str,
        depth: int = 50,
        config: BybitWebSocketConfig | None = None,
        quality_handler: QualityHandler | None = None,
    ) -> None:
        self.symbol = symbol
        self.depth = depth
        self.orderbook = OrderBook(symbol, max_levels=depth)
        self._quality_handler = quality_handler
        self.websocket = BybitWebSocket(
            [f"orderbook.{depth}.{symbol}"],
            self._handle_message,
            config=config,
        )

    @property
    def state(self) -> OrderBookState:
        return self.orderbook.state

    async def run(self) -> None:
        await self.websocket.run()

    async def stop(self) -> None:
        await self.websocket.stop()

    async def _handle_message(self, message: dict[str, Any]) -> None:
        if not message.get("topic", "").startswith("orderbook."):
            return
        quality = self.orderbook.apply(message)
        if quality is None:
            return
        if self._quality_handler is not None:
            await self._quality_handler(quality)
        if quality.code.value in {"orderbook_gap", "impossible_value", "malformed"}:
            raise BybitReconnectRequired(quality.message)
