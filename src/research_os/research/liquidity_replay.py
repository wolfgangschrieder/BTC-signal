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

@dataclass(frozen=True)
class LiquidityReplayDataset:
    symbol: str
    version: str
    outcomes: tuple[LiquidityReplayOutcome, ...]
    skipped: int
    train_count: int
    test_count: int

def build_dataset(points: Iterable[LiquidityReplayPoint], candles: Sequence,
                  direction: str, symbol: str = "BTCUSDT", horizon_minutes: int = 60,
                  train_ratio: float = 0.70) -> LiquidityReplayDataset:
    if not 0.5 <= train_ratio < 1.0:
        raise ValueError("train_ratio must be in [0.5, 1)")
    ordered=sorted(points,key=lambda x:x.timestamp)
    outcomes=[]; skipped=0
    for point in ordered:
        outcome=resolve(point,candles,direction,horizon_minutes)
        if outcome is None:
            skipped += 1
        else:
            outcomes.append(outcome)
    cut=int(len(outcomes)*train_ratio)
    return LiquidityReplayDataset(
        symbol,
        f"liquidity-replay-v1:{horizon_minutes}:{train_ratio}",
        tuple(outcomes),skipped,cut,len(outcomes)-cut)

def chronological_split(dataset: LiquidityReplayDataset):
    return dataset.outcomes[:dataset.train_count], dataset.outcomes[dataset.train_count:]

def summarize_replay(outcomes: Sequence[LiquidityReplayOutcome]):
    returns=[x.realized_return_pct for x in outcomes if x.realized_return_pct is not None]
    if not returns:
        return {"sample_size":0,"mean_return":None,"positive_rate":None}
    return {
        "sample_size":len(returns),
        "mean_return":sum(returns)/len(returns),
        "positive_rate":sum(x>0 for x in returns)/len(returns),
        "mean_mfe":sum(x.mfe_pct for x in outcomes)/len(outcomes),
        "mean_mae":sum(x.mae_pct for x in outcomes)/len(outcomes),
    }
