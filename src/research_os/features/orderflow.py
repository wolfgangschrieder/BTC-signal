from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from collections.abc import Sequence

@dataclass(frozen=True)
class TradeObservation:
    timestamp: datetime
    price: float
    size: float
    side: str
    source: str = "bybit"

@dataclass(frozen=True)
class OrderFlowSnapshot:
    timestamp: datetime
    buy_volume: float | None
    sell_volume: float | None
    delta: float | None
    cumulative_delta: float | None
    trade_count: int
    intensity: float | None
    large_trade_volume: float | None
    large_trade_share: float | None
    imbalance: float | None
    available: bool
    reason: str | None = None
    version: str = "orderflow-v1"

class OrderFlowEngine:
    """Deterministic trade-flow features. Invalid observations remain excluded."""
    version = "orderflow-v1"

    def build(
        self,
        trades: Sequence[TradeObservation],
        timestamp: datetime,
        lookback: int = 200,
        large_trade_quantile: float = 0.90,
    ) -> OrderFlowSnapshot:
        valid=[]
        for trade in trades[-lookback:]:
            side=trade.side.lower()
            if trade.price <= 0 or trade.size <= 0 or side not in {"buy","sell"}:
                continue
            valid.append(trade)
        if not valid:
            return OrderFlowSnapshot(timestamp,None,None,None,None,0,None,None,None,None,False,"no valid trades")

        buy=sum(t.size for t in valid if t.side.lower()=="buy")
        sell=sum(t.size for t in valid if t.side.lower()=="sell")
        total=buy+sell
        delta=buy-sell
        sizes=sorted(t.size for t in valid)
        index=min(len(sizes)-1,max(0,int(round((len(sizes)-1)*large_trade_quantile))))
        threshold=sizes[index]
        large=sum(t.size for t in valid if t.size>=threshold)
        first=valid[0].timestamp
        last=valid[-1].timestamp
        span=max((last-first).total_seconds(),1.0)
        return OrderFlowSnapshot(
            timestamp,buy,sell,delta,delta,len(valid),len(valid)/span,
            large,large/total if total else None,
            delta/total if total else None,True
        )
