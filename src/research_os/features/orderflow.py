from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from collections.abc import Sequence
import asyncio

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
    price_delta_divergence: float | None
    absorption: float | None
    available: bool
    reason: str | None = None
    version: str = "orderflow-v2"

class OrderFlowEngine:
    version = "orderflow-v2"

    async def build_async(self, trades, timestamp, **kwargs):
        """Offload unusually expensive research windows from the asyncio event loop."""
        return await asyncio.to_thread(self.build, trades, timestamp, **kwargs)

    def build(
        self,
        trades: Sequence[TradeObservation],
        timestamp: datetime,
        lookback: int = 200,
        cumulative_delta_base: float = 0.0,
        previous_price: float | None = None,
        previous_cumulative_delta: float | None = None,
        large_trade_quantile: float = 0.90,
    ) -> OrderFlowSnapshot:
        valid=[t for t in trades[-lookback:] if t.price>0 and t.size>0 and t.side.lower() in {"buy","sell"}]
        if not valid:
            return OrderFlowSnapshot(timestamp,None,None,None,cumulative_delta_base,0,None,None,None,None,None,None,False,"no valid trades")
        buy=sum(t.size for t in valid if t.side.lower()=="buy")
        sell=sum(t.size for t in valid if t.side.lower()=="sell")
        total=buy+sell
        delta=buy-sell
        cumulative=cumulative_delta_base+delta
        sizes=sorted(t.size for t in valid)
        index=min(len(sizes)-1,max(0,int(round((len(sizes)-1)*large_trade_quantile))))
        threshold=sizes[index]
        large=sum(t.size for t in valid if t.size>=threshold)
        span=max((valid[-1].timestamp-valid[0].timestamp).total_seconds(),1.0)
        price_change=(valid[-1].price-previous_price)/previous_price if previous_price and previous_price>0 else None
        cvd_change=cumulative-(previous_cumulative_delta if previous_cumulative_delta is not None else cumulative_delta_base)
        divergence=None
        if price_change is not None:
            if price_change>0 and cvd_change<0:
                divergence=-1.0
            elif price_change<0 and cvd_change>0:
                divergence=1.0
            else:
                divergence=0.0
        large_share=large/total if total else None
        absorption=large_share*abs(delta/total) if total else None
        return OrderFlowSnapshot(timestamp,buy,sell,delta,cumulative,len(valid),len(valid)/span,large,large_share,delta/total if total else None,divergence,absorption,True)

def snapshot_features(snapshot: OrderFlowSnapshot) -> dict[str,float|None]:
    return {
        "orderflow_buy_volume": snapshot.buy_volume,
        "orderflow_sell_volume": snapshot.sell_volume,
        "orderflow_delta": snapshot.delta,
        "orderflow_cumulative_delta": snapshot.cumulative_delta,
        "orderflow_trade_count": float(snapshot.trade_count) if snapshot.available else None,
        "orderflow_intensity": snapshot.intensity,
        "orderflow_large_trade_volume": snapshot.large_trade_volume,
        "orderflow_large_trade_share": snapshot.large_trade_share,
        "orderflow_imbalance": snapshot.imbalance,
        "orderflow_price_delta_divergence": snapshot.price_delta_divergence,
        "orderflow_absorption": snapshot.absorption,
    }
