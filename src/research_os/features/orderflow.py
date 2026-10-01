from __future__ import annotations
from dataclasses import dataclass
from research_os.market.types import TradeEvent, OrderSide, OrderflowState

@dataclass(slots=True, frozen=True)
class OrderflowConfig:
    large_trade_threshold: float = 0.0

class OrderflowEngine:
    __slots__=("config",)
    def __init__(self, config: OrderflowConfig|None=None):
        self.config=config or OrderflowConfig()

    def calculate(self, trades: tuple[TradeEvent, ...], *, cumulative_delta: float|None=None) -> OrderflowState:
        if not trades:
            raise ValueError("trades must not be empty")
        buy=0.0; sell=0.0; large=0.0
        for trade in trades:
            if trade.quantity < 0 or trade.price <= 0:
                continue
            if trade.side is OrderSide.BUY:
                buy += trade.quantity
            else:
                sell += trade.quantity
            if self.config.large_trade_threshold > 0 and trade.quantity >= self.config.large_trade_threshold:
                large += trade.quantity
        total=buy+sell
        return OrderflowState(
            timestamp=trades[-1].event_time,
            buy_volume=buy,
            sell_volume=sell,
            delta=buy-sell,
            cumulative_delta=cumulative_delta,
            trade_count=len(trades),
            large_trade_share=(large/total if total else None),
        )
