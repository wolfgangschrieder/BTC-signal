from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from collections.abc import Sequence
from research_os.features.liquidity import LiquidityCluster

@dataclass(frozen=True)
class RiskPolicy:
    max_leverage: float=5.0
    min_leverage: float=1.0
    max_account_risk: float=0.01
    target_risk: float=0.005
    atr_multiplier: float=1.0
    liquidity_buffer_atr: float=0.15
    require_persistent_liquidity: bool=True

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

    def build_levels(self, direction: str, entry: float, atr: float, liquidity_levels: Sequence[LiquidityLevel]=(), liquidity_clusters: Sequence[LiquidityCluster]=()) -> DynamicRiskLevels:
        if entry<=0 or atr<=0 or not isfinite(entry) or not isfinite(atr):
            raise ValueError("entry and atr must be positive finite values")
        side=direction.lower()
        if side not in {"long","short"}:
            raise ValueError("direction must be long or short")
        cluster = self._select_cluster(side, entry, atr, liquidity_clusters)
        liquidity_available = cluster is not None or (any(x.side.lower()=="bid" and x.price < entry for x in liquidity_levels) if side=="long" else any(x.side.lower()=="ask" and x.price > entry for x in liquidity_levels))
        stop = (cluster.center_price - self.policy.liquidity_buffer_atr*atr) if side=="long" and cluster else (cluster.center_price + self.policy.liquidity_buffer_atr*atr) if side=="short" and cluster else self._liquidity_stop(side,entry,atr,liquidity_levels)
        distance=abs(entry-stop)
        if distance<=0:
            stop=entry-atr if side=="long" else entry+atr
            distance=atr
            source="atr_fallback"
        else:
            source="liquidity" if liquidity_available else "atr"
        if side=="long":
            return DynamicRiskLevels(stop,entry+1.5*distance,entry+2.5*distance,entry+3.5*distance,source,cluster.center_price if cluster else (stop if source=="liquidity" else None))
        return DynamicRiskLevels(stop,entry-1.5*distance,entry-2.5*distance,entry-3.5*distance,source,cluster.center_price if cluster else (stop if source=="liquidity" else None))

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

    @staticmethod
    def _select_cluster(side, entry, atr, clusters):
        if atr <= 0: return None
        candidates=[]
        for c in clusters:
            if side=="long" and c.side=="bid" and c.center_price < entry and entry-c.center_price <= 3*atr and (c.persistent or not RiskEngine().policy.require_persistent_liquidity): candidates.append(c)
            if side=="short" and c.side=="ask" and c.center_price > entry and c.center_price-entry <= 3*atr and (c.persistent or not RiskEngine().policy.require_persistent_liquidity): candidates.append(c)
        return max(candidates,key=lambda c:(c.size_percentile,c.total_size),default=None)
