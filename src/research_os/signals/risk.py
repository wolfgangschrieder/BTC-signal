from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from collections.abc import Sequence

@dataclass(frozen=True)
class RiskPolicy:
    max_leverage: float=5.0
    min_leverage: float=1.0
    max_account_risk: float=0.01
    target_risk: float=0.005
    atr_multiplier: float=1.0
    liquidity_buffer_atr: float=0.15

@dataclass(frozen=True)
class LiquidityLevel:
    price: float
    size: float
    side: str
    source: str="orderbook"

@dataclass(frozen=True)
class DynamicRiskLevels:
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    stop_source: str
    liquidity_reference: float | None

class RiskEngine:
    version="risk-v2"

    def __init__(self, policy: RiskPolicy=RiskPolicy()):
        self.policy=policy

    def recommended_leverage(self, entry: float, stop: float, probability: float) -> float:
        if entry<=0 or stop<=0 or not 0<=probability<=1: raise ValueError("invalid risk inputs")
        stop_distance=abs(entry-stop)/entry
        if stop_distance<=0: return self.policy.min_leverage
        lev=self.policy.target_risk/stop_distance
        return max(self.policy.min_leverage,min(self.policy.max_leverage,lev))

    def build_levels(self, direction: str, entry: float, atr: float, liquidity_levels: Sequence[LiquidityLevel]=()) -> DynamicRiskLevels:
        if entry<=0 or atr<=0 or not isfinite(entry) or not isfinite(atr):
            raise ValueError("entry and atr must be positive finite values")
        side=direction.lower()
        if side not in {"long","short"}:
            raise ValueError("direction must be long or short")
        liquidity_available = any(x.side.lower()=="bid" and x.price < entry for x in liquidity_levels) if side=="long" else any(x.side.lower()=="ask" and x.price > entry for x in liquidity_levels)
        stop=self._liquidity_stop(side,entry,atr,liquidity_levels)
        distance=abs(entry-stop)
        if distance<=0:
            stop=entry-atr if side=="long" else entry+atr
            distance=atr
            source="atr_fallback"
        else:
            source="liquidity" if liquidity_available else "atr"
        if side=="long":
            return DynamicRiskLevels(stop,entry+1.5*distance,entry+2.5*distance,entry+3.5*distance,source,stop if source=="liquidity" else None)
        return DynamicRiskLevels(stop,entry-1.5*distance,entry-2.5*distance,entry-3.5*distance,source,stop if source=="liquidity" else None)

    def _liquidity_stop(self, side, entry, atr, levels):
        buffer=self.policy.liquidity_buffer_atr*atr
        if side=="long":
            candidates=[x for x in levels if x.side.lower()=="bid" and x.price < entry]
            if not candidates: return entry-self.policy.atr_multiplier*atr
            pool=max(candidates,key=lambda x:x.size)
            return pool.price-buffer
        candidates=[x for x in levels if x.side.lower()=="ask" and x.price > entry]
        if not candidates: return entry+self.policy.atr_multiplier*atr
        pool=max(candidates,key=lambda x:x.size)
        return pool.price+buffer
