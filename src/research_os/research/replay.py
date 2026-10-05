from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timedelta
from typing import Sequence
from research_os.features.engine import FeatureEngine
from research_os.market.state_builder import MarketStateBuilder
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.probability import ProbabilityEngine,CalibrationSample,CalibrationMetrics
from research_os.signals.engine import SignalEngine
from research_os.signals.models import SignalDirection,SignalResult

@dataclass(frozen=True)
class ReplayCandle:
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
    def __init__(self,feature_engine=None,builder=None,analyzer=None,probability=None,signal_engine=None,horizon_minutes=60,fee_bps=0.0,slippage_bps=0.0):
        if horizon_minutes <= 0: raise ValueError("horizon_minutes must be positive")
        if fee_bps < 0 or slippage_bps < 0: raise ValueError("fee_bps and slippage_bps must be non-negative")
        self.features=feature_engine or FeatureEngine(); self.builder=builder or MarketStateBuilder()
        self.analyzer=analyzer or MarketAnalyzer(); self.probability=probability or ProbabilityEngine()
        self.signal_engine=signal_engine or SignalEngine(); self.horizon_minutes=horizon_minutes
        self.fee_bps=fee_bps; self.slippage_bps=slippage_bps

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
            available=[x for x in rows if (x.point_in_time_available_at or x.event_time) <= decision_time]
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
            trigger_index=rows.index(trigger)
            status,outcome,ret=self._future_outcome(signal,rows,trigger_index,decision_time)
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

    def _future_outcome(self,signal,rows,index,decision_time=None):
        levels=signal.levels
        if levels is None:return "expired",None,None
        decision_time=decision_time or rows[index].event_time
        end=decision_time+timedelta(minutes=self.horizon_minutes)
        raw_entry=(levels.entry_min+levels.entry_max)/2
        filled=False
        entry=None
        slip=self.slippage_bps/10000.0
        fee=self.fee_bps/10000.0
        for c in rows[index+1:]:
            if c.event_time <= decision_time: continue
            if c.event_time>end: break
            if not filled:
                if not (c.low<=raw_entry<=c.high): continue
                entry=raw_entry*(1+slip) if signal.direction is SignalDirection.LONG else raw_entry*(1-slip)
                filled=True
            if signal.direction is SignalDirection.LONG:
                hit_sl=c.low<=levels.stop_loss; hit_tp=c.high>=levels.tp1
                if hit_sl and hit_tp: return "ambiguous",None,None
                if hit_sl:
                    exit_price=levels.stop_loss*(1-slip)
                    return "loss",0,(exit_price-entry)/entry-2*fee
                if hit_tp:
                    exit_price=levels.tp1*(1-slip)
                    return "win",1,(exit_price-entry)/entry-2*fee
            else:
                hit_sl=c.high>=levels.stop_loss; hit_tp=c.low<=levels.tp1
                if hit_sl and hit_tp: return "ambiguous",None,None
                if hit_sl:
                    exit_price=levels.stop_loss*(1+slip)
                    return "loss",0,(entry-exit_price)/entry-2*fee
                if hit_tp:
                    exit_price=levels.tp1*(1+slip)
                    return "win",1,(entry-exit_price)/entry-2*fee
        return "expired",None,None
