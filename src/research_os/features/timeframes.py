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
    version: str="mtf-alignment-v1"

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

    def build(self,symbol:str,bars_1m:list[OHLCVBar],timestamp:datetime)->MultiTimeframeSnapshot:
        snapshots={}
        for timeframe in Timeframe:
            bars=aggregate_bars(bars_1m,timeframe)
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
    )
