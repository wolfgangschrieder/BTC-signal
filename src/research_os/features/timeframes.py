from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from research_os.features.engine import FeatureEngine
from research_os.features.models import FeatureSnapshot

class Timeframe(StrEnum):
    M1="1m"; M5="5m"; M15="15m"; H1="1h"; H4="4h"; D1="1d"

TIMEFRAME_MINUTES={
    Timeframe.M1:1, Timeframe.M5:5, Timeframe.M15:15,
    Timeframe.H1:60, Timeframe.H4:240, Timeframe.D1:1440,
}

@dataclass(frozen=True)
class OHLCVBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass(frozen=True)
class MultiTimeframeSnapshot:
    symbol: str
    timestamp: datetime
    snapshots: dict[Timeframe, FeatureSnapshot]
    version: str="mtf-v1"

@dataclass(frozen=True)
class MultiTimeframeAlignment:
    direction: str
    available_timeframes: tuple[Timeframe,...]
    bullish_timeframes: tuple[Timeframe,...]
    bearish_timeframes: tuple[Timeframe,...]
    conflicting: bool
    state: MultiTimeframeState | None = None
    version: str="mtf-alignment-v2"

@dataclass(frozen=True)
class MultiTimeframeState:
    trend: str
    momentum: str
    volatility: str
    structure: str
    breakout: str
    pullback: str
    alignment: str
    conflict: bool
    strength: float
    version: str="mtf-state-v1"

def _bucket_start(ts: datetime, minutes: int) -> datetime:
    ts=ts.astimezone(timezone.utc)
    epoch=int(ts.timestamp())
    size=minutes*60
    return datetime.fromtimestamp((epoch//size)*size,tz=timezone.utc)

def aggregate_bars(bars: list[OHLCVBar], timeframe: Timeframe, include_partial: bool=False) -> list[OHLCVBar]:
    """Aggregate complete, contiguous 1m bars without inventing missing observations."""
    if timeframe is Timeframe.M1:
        return list(bars)

    minutes=TIMEFRAME_MINUTES[timeframe]
    ordered=sorted(bars,key=lambda x:x.timestamp)
    groups: dict[datetime,list[OHLCVBar]]={}
    for bar in ordered:
        groups.setdefault(_bucket_start(bar.timestamp,minutes),[]).append(bar)

    result=[]
    for start,group in sorted(groups.items()):
        expected=minutes
        complete=len(group)==expected
        contiguous=all(
            group[i].timestamp.astimezone(timezone.utc)
            == group[i-1].timestamp.astimezone(timezone.utc)+timedelta(minutes=1)
            for i in range(1,len(group))
        )
        if not include_partial and (not complete or not contiguous):
            continue
        if not group:
            continue
        result.append(OHLCVBar(
            timestamp=start,
            open=group[0].open,
            high=max(x.high for x in group),
            low=min(x.low for x in group),
            close=group[-1].close,
            volume=sum(x.volume for x in group),
        ))
    return result

class MultiTimeframeFeatureEngine:
    """Builds the same deterministic feature set on 1m-derived higher timeframes."""
    version="mtf-features-v1"

    def __init__(self, feature_engine: FeatureEngine|None=None):
        self.feature_engine=feature_engine or FeatureEngine()

    def build(self,symbol:str,bars_1m:list[OHLCVBar],timestamp:datetime,as_of:datetime|None=None)->MultiTimeframeSnapshot:
        """Build only from bars whose complete availability time is <= as_of."""
        cutoff=as_of or timestamp
        ordered=sorted(bars_1m,key=lambda x:x.timestamp)
        available=[bar for bar in ordered if bar.timestamp.astimezone(timezone.utc)+timedelta(minutes=1) <= cutoff.astimezone(timezone.utc)]
        snapshots={}
        for timeframe in Timeframe:
            bars=aggregate_bars(available,timeframe)
            if not bars:
                snapshots[timeframe]=self.feature_engine.build(symbol,timestamp,[],[],[],[])
                continue
            snapshots[timeframe]=self.feature_engine.build(
                symbol,
                bars[-1].timestamp,
                [x.close for x in bars],
                [x.volume for x in bars],
                [x.high for x in bars],
                [x.low for x in bars],
            )
        return MultiTimeframeSnapshot(symbol,timestamp,snapshots,self.version)

def analyze_alignment(mtf: MultiTimeframeSnapshot)->MultiTimeframeAlignment:
    bullish=[]; bearish=[]; available=[]
    for timeframe,snapshot in mtf.snapshots.items():
        values={x.name:x for x in snapshot.features}
        feature=values.get("return_5") or values.get("return_1")
        if feature is None or not feature.available or feature.value is None or feature.value==0:
            continue
        available.append(timeframe)
        (bullish if feature.value>0 else bearish).append(timeframe)
    if bullish and bearish:
        direction="conflicting"
    elif bullish:
        direction="bullish"
    elif bearish:
        direction="bearish"
    else:
        direction="neutral"
    return MultiTimeframeAlignment(
        direction=direction,
        available_timeframes=tuple(available),
        bullish_timeframes=tuple(bullish),
        bearish_timeframes=tuple(bearish),
        conflicting=bool(bullish and bearish),
        state=classify_mtf_state(mtf),
    )

def _feature(snapshot, name):
    if snapshot is None: return None
    for item in snapshot.features:
        if item.name == name: return item.value if item.available else None
    return None

def classify_mtf_state(mtf):
    returns=[]; vols=[]
    for tf in (Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1):
        snap=mtf.snapshots.get(tf); r=_feature(snap,"return_5"); v=_feature(snap,"realized_vol")
        if r is not None: returns.append(r)
        if v is not None: vols.append(v)
    bullish=sum(x>0 for x in returns); bearish=sum(x<0 for x in returns)
    trend="bullish" if bullish and not bearish else "bearish" if bearish and not bullish else "mixed" if bullish and bearish else "unknown"
    total=sum(returns); momentum="positive" if total>0 else "negative" if total<0 else "neutral"
    avg_vol=sum(vols)/len(vols) if vols else None
    volatility="high" if avg_vol is not None and avg_vol>=0.02 else "low" if avg_vol is not None and avg_vol<=0.003 else "normal" if avg_vol is not None else "unknown"
    r15=_feature(mtf.snapshots.get(Timeframe.M15),"return_5")
    structure="up" if r15 is not None and r15>0 else "down" if r15 is not None and r15<0 else "unknown"
    breakout="active" if r15 is not None and abs(r15)>=0.02 else "none" if r15 is not None else "unknown"
    pullback="possible" if r15 is not None and returns and r15*total<0 else "none" if r15 is not None else "unknown"
    alignment="bullish" if bullish and not bearish else "bearish" if bearish and not bullish else "conflicting" if bullish and bearish else "neutral"
    strength=max(bullish,bearish)/max(len(returns),1)
    return MultiTimeframeState(trend,momentum,volatility,structure,breakout,pullback,alignment,bool(bullish and bearish),strength)
