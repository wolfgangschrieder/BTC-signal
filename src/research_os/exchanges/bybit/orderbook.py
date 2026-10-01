from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from research_os.data.models import QualityCode, QualityEvent


@dataclass(frozen=True)
class OrderBookLevel:
    price: Decimal
    size: Decimal


@dataclass(frozen=True)
class OrderBookState:
    symbol: str
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    update_id: int
    sequence: int | None
    valid: bool
    last_event_time_ms: int
    status: str


class OrderBookError(ValueError):
    pass


class OrderBook:
    """Applies Bybit snapshot/delta messages with sequence validation.

    A gap or invalid update makes the book invalid until a fresh snapshot is
    accepted. Invalid books must not be used for production features/signals.
    """

    def __init__(self, symbol: str, max_levels: int = 50) -> None:
        if max_levels <= 0:
            raise ValueError("max_levels must be positive")
        self.symbol = symbol
        self.max_levels = max_levels
        self._bids: dict[Decimal, Decimal] = {}
        self._asks: dict[Decimal, Decimal] = {}
        self._update_id: int | None = None
        self._sequence: int | None = None
        self._last_event_time_ms = 0
        self._valid = False
        self._status = "awaiting_snapshot"

    @property
    def state(self) -> OrderBookState:
        return OrderBookState(
            symbol=self.symbol,
            bids=tuple(
                OrderBookLevel(price, size)
                for price, size in sorted(self._bids.items(), reverse=True)[: self.max_levels]
            ),
            asks=tuple(
                OrderBookLevel(price, size)
                for price, size in sorted(self._asks.items())[: self.max_levels]
            ),
            update_id=self._update_id or 0,
            sequence=self._sequence,
            valid=self._valid,
            last_event_time_ms=self._last_event_time_ms,
            status=self._status,
        )

    def apply(self, message: dict[str, Any]) -> QualityEvent | None:
        topic = message.get("topic", "")
        if not topic.startswith("orderbook."):
            raise OrderBookError("message is not an orderbook topic")

        data = message.get("data")
        if not isinstance(data, dict):
            return self._invalidate(
                QualityCode.MALFORMED, "orderbook data is not an object"
            )

        msg_type = message.get("type")
        if msg_type == "snapshot":
            return self._apply_snapshot(message, data)
        if msg_type == "delta":
            return self._apply_delta(message, data)
        return self._invalidate(QualityCode.MALFORMED, "unknown orderbook message type")

    def _apply_snapshot(self, message: dict[str, Any], data: dict[str, Any]) -> QualityEvent | None:
        try:
            bids = self._parse_side(data.get("b", []))
            asks = self._parse_side(data.get("a", []))
            update_id = int(data["u"])
            sequence = int(data["seq"]) if data.get("seq") is not None else None
            event_time = int(message["ts"])
        except (KeyError, TypeError, ValueError) as exc:
            return self._invalidate(QualityCode.MALFORMED, f"invalid snapshot: {exc}")

        if not bids and not asks:
            return self._invalidate(QualityCode.MALFORMED, "empty orderbook snapshot")

        self._bids = {level.price: level.size for level in bids if level.size > 0}
        self._asks = {level.price: level.size for level in asks if level.size > 0}
        self._update_id = update_id
        self._sequence = sequence
        self._last_event_time_ms = event_time
        self._valid = True
        self._status = "valid"
        return None

    def _apply_delta(self, message: dict[str, Any], data: dict[str, Any]) -> QualityEvent | None:
        if not self._valid or self._update_id is None:
            return self._invalidate(
                QualityCode.ORDERBOOK_GAP, "delta received before a valid snapshot"
            )

        try:
            update_id = int(data["u"])
            sequence = int(data["seq"]) if data.get("seq") is not None else None
            event_time = int(message["ts"])
            bids = self._parse_side(data.get("b", []))
            asks = self._parse_side(data.get("a", []))
        except (KeyError, TypeError, ValueError) as exc:
            return self._invalidate(QualityCode.MALFORMED, f"invalid delta: {exc}")

        if update_id <= self._update_id:
            return QualityEvent(
                code=QualityCode.DUPLICATE,
                source="bybit",
                message="stale or duplicate orderbook update",
                details={"update_id": update_id, "last_update_id": self._update_id},
            )

        if sequence is not None and self._sequence is not None and sequence < self._sequence:
            return self._invalidate(
                QualityCode.ORDERBOOK_GAP,
                "orderbook sequence moved backwards",
            )

        self._apply_levels(self._bids, bids)
        self._apply_levels(self._asks, asks)
        self._update_id = update_id
        self._sequence = sequence if sequence is not None else self._sequence
        self._last_event_time_ms = event_time

        if self._crossed():
            return self._invalidate(QualityCode.IMPOSSIBLE_VALUE, "orderbook became crossed")

        return None

    @staticmethod
    def _parse_side(raw: Any) -> list[OrderBookLevel]:
        if not isinstance(raw, list):
            raise ValueError("orderbook side must be a list")
        levels: list[OrderBookLevel] = []
        for item in raw:
            if not isinstance(item, list) or len(item) != 2:
                raise ValueError("orderbook level must be [price, size]")
            price = Decimal(str(item[0]))
            size = Decimal(str(item[1]))
            if price <= 0 or size < 0:
                raise ValueError("price must be > 0 and size must be >= 0")
            levels.append(OrderBookLevel(price, size))
        return levels

    @staticmethod
    def _apply_levels(book: dict[Decimal, Decimal], levels: list[OrderBookLevel]) -> None:
        for level in levels:
            if level.size == 0:
                book.pop(level.price, None)
            else:
                book[level.price] = level.size

    def _crossed(self) -> bool:
        if not self._bids or not self._asks:
            return False
        return max(self._bids) >= min(self._asks)

    def _invalidate(self, code: QualityCode, message: str) -> QualityEvent:
        self._valid = False
        self._status = "invalid"
        return QualityEvent(
            code=code,
            source="bybit",
            message=message,
            details={"symbol": self.symbol},
        )
