from __future__ import annotations
from research_os.intelligence.models import AnalysisResult, EvidenceDirection
from research_os.intelligence.probability import ProbabilityResult
from research_os.signals.models import SignalDirection, SignalLevels, SignalResult
from research_os.signals.risk import RiskEngine

class SignalEngine:
    version="signal-v1"
    def __init__(self,risk: RiskEngine|None=None,min_probability: float=.70,min_rr: float=1.5):
        self.risk=risk or RiskEngine(); self.min_probability=min_probability; self.min_rr=min_rr
    def build(self, analysis: AnalysisResult, probability: ProbabilityResult, price: float, atr: float|None=None) -> SignalResult:
        if price<=0: raise ValueError("price must be positive")
        direction=SignalDirection.NONE
        p=0.0
        if probability.long>=self.min_probability and probability.long>probability.short and analysis.direction is EvidenceDirection.BULLISH:
            direction,p=SignalDirection.LONG,probability.long
        elif probability.short>=self.min_probability and probability.short>probability.long and analysis.direction is EvidenceDirection.BEARISH:
            direction,p=SignalDirection.SHORT,probability.short
        if direction is SignalDirection.NONE or atr is None or atr<=0:
            return SignalResult(analysis.symbol,analysis.timestamp,direction,p,probability.no_signal,None,0.0,1.0,("insufficient validated signal conditions",),("missing/insufficient volatility input",),self.version)
        risk_distance=atr
        if direction is SignalDirection.LONG:
            entry_min,entry_max=price-0.15*atr,price+0.15*atr; stop=price-risk_distance; t1=price+1.5*atr;t2=price+2.5*atr;t3=price+3.5*atr
        else:
            entry_min,entry_max=price-0.15*atr,price+0.15*atr; stop=price+risk_distance;t1=price-1.5*atr;t2=price-2.5*atr;t3=price-3.5*atr
        risk=abs(price-stop); rr1=abs(t1-price)/risk; rr2=abs(t2-price)/risk; rr3=abs(t3-price)/risk
        if rr1<self.min_rr:
            return SignalResult(analysis.symbol,analysis.timestamp,SignalDirection.NONE,0.0,probability.no_signal,None,0.0,1.0,("TP1 risk/reward below policy threshold",),(),self.version)
        ev=p*rr1-(1-p)
        lev=self.risk.recommended_leverage(price,stop,p)
        return SignalResult(analysis.symbol,analysis.timestamp,direction,p,probability.no_signal,
            SignalLevels(entry_min,entry_max,stop,t1,t2,t3,rr1,rr2,rr3),ev,lev,
            tuple(e.reason for e in analysis.evidence if e.direction is direction and e.reason),("volatility expansion can invalidate levels","market structure may change before entry"),self.version)
