from __future__ import annotations
from dataclasses import dataclass
from .models import CrossMarketSnapshot

@dataclass(frozen=True)
class CrossMarketState:
    risk_sentiment: str
    dollar_regime: str
    volatility_regime: str
    equity_regime: str
    crypto_beta_regime: str
    alignment: str
    strength: float
    available: bool
    version: str="cross-market-state-v1"

def classify(snapshot: CrossMarketSnapshot) -> CrossMarketState:
    v=snapshot.values
    available=sum(bool(snapshot.availability.get(k)) for k in v)
    if not available:
        return CrossMarketState("unknown","unknown","unknown","unknown","unknown","unknown",0.0,False)
    dxy=v.get("DXY_return"); nasdaq=v.get("NASDAQ_return"); spx=v.get("SPX_return"); vix=v.get("VIX_return")
    dollar="strong" if dxy is not None and dxy>0 else "weak" if dxy is not None and dxy<0 else "neutral"
    equities="risk_on" if ((nasdaq is not None and nasdaq>0) or (spx is not None and spx>0)) else "risk_off" if ((nasdaq is not None and nasdaq<0) or (spx is not None and spx<0)) else "neutral"
    volatility="rising" if vix is not None and vix>0 else "falling" if vix is not None and vix<0 else "neutral"
    risk_on=equities=="risk_on" and dollar=="weak" and volatility=="falling"
    risk_off=equities=="risk_off" and dollar=="strong" and volatility=="rising"
    sentiment="risk_on" if risk_on else "risk_off" if risk_off else "mixed"
    alignment="aligned" if risk_on or risk_off else "mixed"
    strength=min(1.0, sum(x for x in [dxy is not None,nasdaq is not None,spx is not None,vix is not None] if x)/4)
    return CrossMarketState(sentiment,dollar,volatility,equities,"unknown",alignment,strength,True)
