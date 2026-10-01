from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from datetime import datetime
from research_os.signals.models import SignalDirection, SignalResult

class OrderSide(StrEnum):
    BUY="buy"
    SELL="sell"

class OrderType(StrEnum):
    LIMIT="limit"
    MARKET="market"

@dataclass(frozen=True)
class OrderIntent:
    signal_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    limit_price: float | None
    stop_loss: float
    take_profit: float
    created_at: datetime
    client_order_id: str

    @classmethod
    def from_signal(cls, signal: SignalResult, quantity: float, now: datetime) -> "OrderIntent":
        if signal.direction is SignalDirection.NONE:
            raise ValueError("cannot create an order intent from NO SIGNAL")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        if signal.levels is None:
            raise ValueError("signal levels are required")
        side=OrderSide.BUY if signal.direction is SignalDirection.LONG else OrderSide.SELL
        return cls(signal.signal_id,signal.symbol,side,OrderType.LIMIT,quantity,
                   (signal.levels.entry_min+signal.levels.entry_max)/2,
                   signal.levels.stop_loss,signal.levels.tp1,now,
                   f"rs-{signal.signal_id[:24]}")
