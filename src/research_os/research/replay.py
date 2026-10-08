from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from research_os.features.engine import FeatureEngine
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.probability import (
    CalibrationMetrics,
    CalibrationSample,
    ProbabilityEngine,
)
from research_os.market.state_builder import MarketStateBuilder
from research_os.signals.engine import SignalEngine
from research_os.signals.execution import ExecutionStatus, evaluate_candle
from research_os.signals.models import SignalDirection, SignalResult


@dataclass(frozen=True)
class ReplayCandle:
    # Candle open time. Explicit availability is required for delayed/closed bars.
    event_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float=0.0
    point_in_time_available_at: datetime|None=None

@dataclass(frozen=True)
class ReplayResult:
    timestamp: datetime
    signal: SignalResult
    outcome: int|None
    outcome_status: str
    return_pct: float|None
    features: dict[str,float|None]

@dataclass(frozen=True)
class ReplayReport:
    symbol: str
    dataset_version: str
    model_versions: tuple[str,...]
    results: tuple[ReplayResult,...]
    signals: int
    resolved: int
    wins: int
    losses: int
    expired: int
    win_rate: float|None
    brier: float
    log_loss: float

    @property
    def ambiguous(self) -> int:
        """Signals whose OHLC candle cannot establish TP/SL ordering."""
        return sum(result.outcome_status == "ambiguous" for result in self.results)

    @property
    def unresolved(self) -> int:
        """Signals excluded from win/loss scoring (expired or ambiguous)."""
        return sum(result.outcome is None for result in self.results)

class ReplayEngine:
    """Deterministic historical replay with a strict point-in-time information boundary."""
    def __init__(self,feature_engine=None,builder=None,analyzer=None,probability=None,signal_engine=None,horizon_minutes=60,fee_bps=0.0,slippage_bps=0.0, conservative_entry=True):
        if horizon_minutes <= 0: raise ValueError("horizon_minutes must be positive")
        if fee_bps < 0 or slippage_bps < 0: raise ValueError("fee_bps and slippage_bps must be non-negative")
        self.features=feature_engine or FeatureEngine(); self.builder=builder or MarketStateBuilder()
        self.analyzer=analyzer or MarketAnalyzer(); self.probability=probability or ProbabilityEngine()
        self.signal_engine=signal_engine or SignalEngine(); self.horizon_minutes=horizon_minutes
        self.fee_bps=fee_bps; self.slippage_bps=slippage_bps
        self.conservative_entry=conservative_entry

    def run(self,symbol:str,candles:Sequence[ReplayCandle],dataset_version="replay-v1")->ReplayReport:
        # Event-time order is required for feature construction and future outcomes.
        rows=sorted(candles,key=lambda x:x.event_time)
        # Decision-time order is required for PIT correctness. A delayed candle can become
        # available after later-event candles, so iterating event-time order can move the
        # simulated clock backwards.
        decisions=sorted(
            ((x.point_in_time_available_at or x.event_time, x) for x in rows),
            key=lambda item:(item[0],item[1].event_time),
        )
        results=[]; seen_decisions=set()
        for decision_time, trigger in decisions:
            if decision_time in seen_decisions:
                continue
            seen_decisions.add(decision_time)
            available=[x for x in rows if x.event_time <= decision_time and (x.point_in_time_available_at or x.event_time) <= decision_time]
            closes=[x.close for x in available]
            volumes=[x.volume for x in available]
            highs=[x.high for x in available]
            lows=[x.low for x in available]
            if len(closes)<6: continue
            snap=self.features.build(symbol,decision_time,closes,volumes,highs,lows)
            state=self.builder.build(symbol,decision_time,decision_time,decision_time,snap,{})
            analysis=self.analyzer.analyze(state); prob=self.probability.predict(analysis)
            decision_price=available[-1].close
            signal=self.signal_engine.build(
                analysis,prob,decision_price,
                next((f.value for f in snap.features if f.name == "atr_14" and f.available), None),
            )
            if signal.direction is SignalDirection.NONE: continue
            status,outcome,ret=self._future_outcome(signal,rows,decision_time)
            results.append(ReplayResult(decision_time,signal,outcome,status,ret,dict(state.values)))
        resolved=[x for x in results if x.outcome is not None]
        wins=sum(x.outcome==1 for x in resolved if x.outcome_status=="win")
        losses=sum(x.outcome==0 for x in resolved if x.outcome_status=="loss")
        expired=sum(x.outcome_status=="expired" for x in results)
        scored=[x for x in resolved if x.outcome_status in ("win","loss")]
        samples=[CalibrationSample(x.signal.probability,x.outcome or 0) for x in scored]
        return ReplayReport(symbol,dataset_version,(self.features.version,self.analyzer.version,self.probability.version,self.signal_engine.version),
            tuple(results),len(results),len(scored),wins,losses,expired,wins/(wins+losses) if wins+losses else None,
            CalibrationMetrics.brier(samples),CalibrationMetrics.log_loss(samples))

    def _future_outcome(self,signal,rows,decision_time):
        levels=signal.levels
        if levels is None:return "expired",None,None
        end=decision_time+timedelta(minutes=self.horizon_minutes)
        raw_entry=(levels.entry_min+levels.entry_max)/2
        filled=False
        entry=None
        for candle in rows:
            if candle.event_time <= decision_time: continue
            if candle.event_time > end: break
            if not filled:
                fill=evaluate_candle(
                    signal.direction, entry_price=raw_entry,
                    stop_loss=levels.stop_loss, take_profit=levels.tp1,
                    high=candle.high, low=candle.low,
                    fee_bps=self.fee_bps, slippage_bps=self.slippage_bps,
                    check_exit=False, conservative_entry=self.conservative_entry,
                )
                if fill.status is ExecutionStatus.NO_FILL: continue
                if fill.status is ExecutionStatus.AMBIGUOUS: return "ambiguous",None,None
                filled=True
                entry=fill.entry_price
                continue
            result=evaluate_candle(
                signal.direction, entry_price=entry,
                stop_loss=levels.stop_loss, take_profit=levels.tp1,
                high=candle.high, low=candle.low,
                fee_bps=self.fee_bps, slippage_bps=self.slippage_bps,
                check_exit=True, entry_filled=True,
            )
            if result.status in (ExecutionStatus.NO_FILL,ExecutionStatus.PENDING): continue
            if result.status is ExecutionStatus.WIN: return "win",1,result.realized_return
            if result.status is ExecutionStatus.LOSS: return "loss",0,result.realized_return
            return "ambiguous",None,None
        return "expired",None,None
