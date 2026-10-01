from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict
from research_os.research.replay import ReplayResult

class Regime(str,Enum):
    TREND="trend"
    RANGE="range"
    HIGH_VOLATILITY="high_volatility"
    LOW_VOLATILITY="low_volatility"
    UNKNOWN="unknown"

@dataclass(frozen=True)
class RegimeStats:
    regime: Regime
    signals: int
    resolved: int
    wins: int
    losses: int
    expired: int
    win_rate: float|None
    avg_return: float|None

@dataclass(frozen=True)
class RegimeReport:
    stats: tuple[RegimeStats,...]

class RegimeClassifier:
    version="regime-v1"
    def classify(self,features:dict[str,float|None])->Regime:
        ret=features.get("return_5"); vol=features.get("realized_vol")
        if ret is None or vol is None:return Regime.UNKNOWN
        if vol>=0.02:return Regime.HIGH_VOLATILITY
        if vol<=0.003:return Regime.LOW_VOLATILITY
        if abs(ret)<0.005:return Regime.RANGE
        return Regime.TREND

class RegimeAnalyzer:
    def __init__(self,classifier=None):self.classifier=classifier or RegimeClassifier()
    def analyze(self,rows:list[tuple[ReplayResult,dict[str,float|None]]])->RegimeReport:
        groups=defaultdict(list)
        for result,features in rows:groups[self.classifier.classify(features)].append(result)
        out=[]
        for regime,items in sorted(groups.items(),key=lambda x:x[0].value):
            resolved=[x for x in items if x.outcome_status in ("win","loss")]
            wins=sum(x.outcome_status=="win" for x in resolved); losses=sum(x.outcome_status=="loss" for x in resolved)
            returns=[x.return_pct for x in resolved if x.return_pct is not None]
            out.append(RegimeStats(regime,len(items),len(resolved),wins,losses,sum(x.outcome_status=="expired" for x in items),
                wins/(wins+losses) if wins+losses else None,sum(returns)/len(returns) if returns else None))
        return RegimeReport(tuple(out))
