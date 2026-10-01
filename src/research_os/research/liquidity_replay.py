from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Sequence
from research_os.features.liquidity import LiquidityEngine, LiquidityState
from research_os.signals.risk import RiskEngine, DynamicRiskLevels

@dataclass(frozen=True)
class LiquidityReplayPoint:
    timestamp: datetime
    price: float
    atr: float
    liquidity_valid: bool
    stop_source: str
    stop_loss: float
    tp1: float
    liquidity_reference: float | None

@dataclass(frozen=True)
class LiquidityReplayOutcome:
    point: LiquidityReplayPoint
    horizon_minutes: int
    status: str
    realized_return_pct: float | None
    mfe_pct: float | None
    mae_pct: float | None
    resolved_at: datetime | None

def build_risk_point(timestamp: datetime, price: float, atr: float, direction: str,
                     liquidity: LiquidityState | None, risk: RiskEngine | None = None) -> LiquidityReplayPoint:
    if price <= 0 or atr <= 0:
        raise ValueError("price and atr must be positive")
    risk = risk or RiskEngine()
    clusters = ()
    if liquidity is not None and liquidity.valid:
        clusters = tuple(liquidity.bid_clusters + liquidity.ask_clusters)
    levels = risk.build_levels(direction, price, atr, (), clusters)
    return LiquidityReplayPoint(timestamp, price, atr, bool(liquidity and liquidity.valid),
                                levels.stop_source, levels.stop_loss, levels.tp1,
                                levels.liquidity_reference)

def resolve(point: LiquidityReplayPoint, candles: Sequence, direction: str,
            horizon_minutes: int = 60) -> LiquidityReplayOutcome | None:
    if horizon_minutes <= 0:
        raise ValueError("horizon_minutes must be positive")
    target = point.timestamp + timedelta(minutes=horizon_minutes)
    window = [c for c in candles if point.timestamp < c.timestamp <= target]
    if not window or window[-1].timestamp < target:
        return None
    entry = point.price
    mfe = 0.0
    mae = 0.0
    for candle in window:
        high, low = float(candle.high), float(candle.low)
        if direction == "long":
            mfe=max(mfe,(high-entry)/entry); mae=min(mae,(low-entry)/entry)
            hit_sl=low <= point.stop_loss; hit_tp=high >= point.tp1
            if hit_sl or hit_tp:
                return LiquidityReplayOutcome(point,horizon_minutes,
                    "loss" if hit_sl else "win",
                    ((point.stop_loss if hit_sl else point.tp1)-entry)/entry,
                    mfe,mae,candle.timestamp)
        elif direction == "short":
            mfe=max(mfe,(entry-low)/entry); mae=min(mae,(high-entry)/entry)
            hit_sl=high >= point.stop_loss; hit_tp=low <= point.tp1
            if hit_sl or hit_tp:
                exit_price=point.stop_loss if hit_sl else point.tp1
                return LiquidityReplayOutcome(point,horizon_minutes,
                    "loss" if hit_sl else "win",
                    (entry-exit_price)/entry,mfe,mae,candle.timestamp)
        else:
            raise ValueError("direction must be long or short")
    final=float(window[-1].close)
    ret=(final-entry)/entry if direction=="long" else (entry-final)/entry
    return LiquidityReplayOutcome(point,horizon_minutes,"expired",ret,mfe,mae,window[-1].timestamp)

def replay(points: Iterable[LiquidityReplayPoint], candles: Sequence, direction: str,
           horizon_minutes: int = 60) -> tuple[LiquidityReplayOutcome, ...]:
    results=[]
    for point in sorted(points,key=lambda x:x.timestamp):
        outcome=resolve(point,candles,direction,horizon_minutes)
        if outcome is not None:
            results.append(outcome)
    return tuple(results)
