from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

class DerivativesRegime(str, Enum):
    UNKNOWN="unknown"
    NEUTRAL="neutral"
    POSITIVE_FUNDING="positive_funding"
    NEGATIVE_FUNDING="negative_funding"
    OI_RISING="oi_rising"
    OI_FALLING="oi_falling"
    LIQUIDATION_STRESS="liquidation_stress"


@dataclass(frozen=True)
class DerivativesState:
    funding_regime: str
    oi_regime: str
    positioning: str
    liquidation_stress: str
    price_oi_relationship: str
    funding_price_relationship: str
    alignment: str
    strength: float
    available: bool
    version: str = "derivatives-state-v1"


@dataclass(frozen=True)
class DerivativesSnapshot:
    timestamp: datetime
    funding_rate: float | None
    open_interest: float | None
    oi_change: float | None
    price_oi_divergence: float | None
    funding_price_divergence: float | None
    liquidation_long: float | None
    liquidation_short: float | None
    liquidation_imbalance: float | None
    available: bool
    reason: str | None = None
    state: DerivativesState | None = None
    version: str = "derivatives-v1"

class DerivativesEngine:
    version="derivatives-v1"

    def build(self, timestamp, price, funding_rate=None, open_interest=None,
              previous_price=None, previous_funding_rate=None,
              previous_open_interest=None, liquidation_long=0.0,
              liquidation_short=0.0):
        oi_change=None
        if open_interest is not None and previous_open_interest is not None and previous_open_interest != 0:
            oi_change=(open_interest-previous_open_interest)/abs(previous_open_interest)
        price_change=None
        if price is not None and previous_price is not None and previous_price != 0:
            price_change=(price-previous_price)/abs(previous_price)
        price_oi_div=None
        if price_change is not None and oi_change is not None:
            if price_change > 0 and oi_change < 0: price_oi_div=-1.0
            elif price_change < 0 and oi_change > 0: price_oi_div=1.0
            else: price_oi_div=0.0
        funding_div=None
        if funding_rate is not None and previous_funding_rate is not None:
            funding_delta=funding_rate-previous_funding_rate
            if price_change is not None:
                if price_change > 0 and funding_delta < 0: funding_div=1.0
                elif price_change < 0 and funding_delta > 0: funding_div=-1.0
                else: funding_div=0.0
        total=liquidation_long+liquidation_short
        liq_imb=(liquidation_long-liquidation_short)/total if total else None
        available=any(x is not None for x in (funding_rate,open_interest,liq_imb))
        state=classify_derivatives_state(funding_rate, oi_change, price_oi_div, funding_div, liquidation_long, liquidation_short, liq_imb, available)
        return DerivativesSnapshot(timestamp,funding_rate,open_interest,oi_change,price_oi_div,funding_div,liquidation_long,liquidation_short,liq_imb,available,None if available else "no derivatives data",state)

def classify_derivatives_state(funding_rate, oi_change, price_oi_divergence,
                              funding_price_divergence, liquidation_long,
                              liquidation_short, liquidation_imbalance, available):
    if not available:
        return DerivativesState("unknown","unknown","unknown","unknown","unknown","unknown","unknown",0.0,False)
    funding_regime = "positive_funding" if funding_rate is not None and funding_rate > 0 else "negative_funding" if funding_rate is not None and funding_rate < 0 else "neutral"
    oi_regime = "rising" if oi_change is not None and oi_change > 0 else "falling" if oi_change is not None and oi_change < 0 else "neutral"
    total_liq=(liquidation_long or 0.0)+(liquidation_short or 0.0)
    stress="high" if total_liq > 0 else "none"
    price_oi = "bearish_divergence" if price_oi_divergence == -1 else "bullish_divergence" if price_oi_divergence == 1 else "aligned_or_neutral"
    funding_price = "bullish_divergence" if funding_price_divergence == 1 else "bearish_divergence" if funding_price_divergence == -1 else "aligned_or_neutral"
    signals=sum(x != "aligned_or_neutral" for x in (price_oi,funding_price))
    conflicting=(price_oi == "bullish_divergence" and funding_price == "bearish_divergence") or (price_oi == "bearish_divergence" and funding_price == "bullish_divergence")
    alignment="conflicting" if conflicting else "neutral"
    strength=min(1.0, 0.25*signals + (0.25 if abs(liquidation_imbalance or 0) >= 0.5 else 0.0))
    positioning="crowded_long" if funding_rate is not None and funding_rate > 0 and oi_change is not None and oi_change > 0 else "crowded_short" if funding_rate is not None and funding_rate < 0 and oi_change is not None and oi_change > 0 else "mixed"
    return DerivativesState(funding_regime,oi_regime,positioning,stress,price_oi,funding_price,alignment,strength,True)


def snapshot_features(snapshot):
    return {
        "derivatives_funding_rate": snapshot.funding_rate,
        "derivatives_open_interest": snapshot.open_interest,
        "derivatives_oi_change": snapshot.oi_change,
        "derivatives_price_oi_divergence": snapshot.price_oi_divergence,
        "derivatives_funding_price_divergence": snapshot.funding_price_divergence,
        "derivatives_liquidation_long": snapshot.liquidation_long,
        "derivatives_liquidation_short": snapshot.liquidation_short,
        "derivatives_liquidation_imbalance": snapshot.liquidation_imbalance,
    }
