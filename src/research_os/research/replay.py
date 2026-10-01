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

class ReplayEngine:
    """Deterministic historical replay with a strict point-in-time information boundary."""
    def __init__(self,feature_engine=None,builder=None,analyzer=None,probability=None,signal_engine=None,horizon_minutes=60):
        self.features=feature_engine or FeatureEngine(); self.builder=builder or MarketStateBuilder()
        self.analyzer=analyzer or MarketAnalyzer(); self.probability=probability or ProbabilityEngine()
        self.signal_engine=signal_engine or SignalEngine(); self.horizon_minutes=horizon_minutes

    def run(self,symbol:str,candles:Sequence[ReplayCandle],dataset_version="replay-v1")->ReplayReport:
        rows=sorted(candles,key=lambda x:x.event_time)
        results=[]; closes=[]; volumes=[]
        for i,c in enumerate(rows):
            pit=c.point_in_time_available_at or c.event_time
            if pit>c.event_time: raise ValueError("replay candle availability cannot be after decision timestamp")
            closes.append(c.close); volumes.append(c.volume)
            if len(closes)<6: continue
            snap=self.features.build(symbol,c.event_time,closes,volumes)
            state=self.builder.build(symbol,c.event_time,c.event_time,pit,snap,{})
            analysis=self.analyzer.analyze(state); prob=self.probability.predict(analysis)
            signal=self.signal_engine.build(analysis,prob,c.close,self._atr_proxy(rows[:i+1]))
            if signal.direction is SignalDirection.NONE: continue
            status,outcome,ret=self._future_outcome(signal,rows,i)
            results.append(ReplayResult(c.event_time,signal,outcome,status,ret))
        resolved=[x for x in results if x.outcome is not None]
        wins=sum(x.outcome==1 for x in resolved if x.outcome_status=="win")
        losses=sum(x.outcome==0 for x in resolved if x.outcome_status=="loss")
        expired=sum(x.outcome_status=="expired" for x in results)
        scored=[x for x in resolved if x.outcome_status in ("win","loss")]
        samples=[CalibrationSample(x.signal.probability,x.outcome or 0) for x in scored]
        return ReplayReport(symbol,dataset_version,(self.features.version,self.analyzer.version,self.probability.version,self.signal_engine.version),
            tuple(results),len(results),len(scored),wins,losses,expired,wins/(wins+losses) if wins+losses else None,
            CalibrationMetrics.brier(samples),CalibrationMetrics.log_loss(samples))

    def _atr_proxy(self,rows):
        if len(rows)<2:return None
        recent=rows[-15:]
        return sum(abs(x.close-y.close) for x,y in zip(recent[1:],recent[:-1]))/max(1,len(recent)-1)

    def _future_outcome(self,signal,rows,index):
        levels=signal.levels
        if levels is None:return "expired",None,None
        end=rows[index].event_time+timedelta(minutes=self.horizon_minutes)
        entry=(levels.entry_min+levels.entry_max)/2
        filled=False
        for c in rows[index+1:]:
            if c.event_time>end:break
            if not filled:
                if not (c.low<=entry<=c.high): continue
                filled=True
            if signal.direction is SignalDirection.LONG:
                hit_sl=c.low<=levels.stop_loss; hit_tp=c.high>=levels.tp1
                if hit_sl or hit_tp:
                    if hit_sl:
                        return "loss",0,(levels.stop_loss-entry)/entry
                    return "win",1,(levels.tp1-entry)/entry
            else:
                hit_sl=c.high>=levels.stop_loss; hit_tp=c.low<=levels.tp1
                if hit_sl or hit_tp:
                    if hit_sl:
                        return "loss",0,(entry-levels.stop_loss)/entry
                    return "win",1,(entry-levels.tp1)/entry
        return "expired",None,None
