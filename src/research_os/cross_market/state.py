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
    version: str="cross-market-state-v2"

def _sign(value, positive, negative):
    if value is None or value == 0:
        return "neutral"
    return positive if value > 0 else negative

def classify(snapshot: CrossMarketSnapshot) -> CrossMarketState:
    v=snapshot.values
    keys=("DXY_return","NASDAQ_return","SPX_return","VIX_return")
    available_count=sum(snapshot.availability.get(k,False) and v.get(k) is not None for k in keys)
    if not available_count:
        return CrossMarketState("unknown","unknown","unknown","unknown","unknown","unknown",0.0,False)
    dollar=_sign(v.get("DXY_return"),"strong","weak")
    volatility=_sign(v.get("VIX_return"),"rising","falling")
    eq=[v.get("NASDAQ_return"),v.get("SPX_return")]
    eq=[x for x in eq if x is not None]
    if not eq:
        equities="unknown"
    elif all(x > 0 for x in eq):
        equities="risk_on"
    elif all(x < 0 for x in eq):
        equities="risk_off"
    else:
        equities="mixed"
    risk_on=equities=="risk_on" and dollar=="weak" and volatility=="falling"
    risk_off=equities=="risk_off" and dollar=="strong" and volatility=="rising"
    sentiment="risk_on" if risk_on else "risk_off" if risk_off else "mixed"
    alignment="aligned" if risk_on or risk_off else "mixed"
    strength=available_count/len(keys)
    return CrossMarketState(sentiment,dollar,volatility,equities,"unknown",alignment,strength,True)
