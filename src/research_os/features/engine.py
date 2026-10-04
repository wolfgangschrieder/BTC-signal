from __future__ import annotations
from datetime import datetime, timezone
from math import log
from statistics import mean, pstdev
from collections.abc import Sequence
from .models import FeatureSnapshot, FeatureValue

class FeatureEngine:
    """Pure, deterministic features. Missing inputs remain unavailable; never fabricated."""
    version = "features-v1"

    def build(self, symbol: str, timestamp: datetime, closes: Sequence[float], volumes: Sequence[float] = (), highs: Sequence[float] = (), lows: Sequence[float] = (), orderbook=None) -> FeatureSnapshot:
        """Build deterministic features with bounded allocations for the live hot path."""
        values: list[FeatureValue] = []
        def add(name, value, available=True, reason=None):
            values.append(FeatureValue(name, value, available, "derived", timestamp, reason))
        n=len(closes)
        if n >= 2 and closes[-2] > 0 and closes[-1] > 0:
            last_return=(closes[-1]/closes[-2])-1.0
            add("return_1", last_return)
            add("log_return_1", log(closes[-1]/closes[-2]))
        else:
            add("return_1", None, False, "need at least 2 positive closes")
            add("log_return_1", None, False, "need at least 2 positive closes")
        if n >= 6:
            base=closes[-6]
            valid_base=base > 0 and closes[-1] > 0
            add("return_5",(closes[-1]/base)-1.0 if valid_base else None,valid_base,"non-positive base" if not valid_base else None)
        else:
            add("return_5", None, False, "need at least 6 closes")
        if n >= 2:
            count=0; mean_return=0.0; m2=0.0; prev=closes[0]
            for close in closes[1:]:
                if prev > 0 and close > 0:
                    value=(close/prev)-1.0
                    count+=1
                    delta=value-mean_return
                    mean_return+=delta/count
                    m2+=delta*(value-mean_return)
                prev=close
            available=count >= 2
            add("realized_vol",(m2/count)**0.5 if available else None,available,"need at least 2 returns")
        else:
            add("realized_vol", None, False, "need at least 2 closes")
        if volumes:
            total_volume=0.0
            for volume in volumes:
                total_volume+=volume
            add("volume_mean",total_volume/len(volumes),True)
        else:
            add("volume_mean",None,False,"volume unavailable")
        if n >= 2 and len(highs)==n and len(lows)==n:
            tr_sum=0.0; tr_count=0
            start=max(1,n-14)
            for i in range(start,n):
                high=highs[i]; low=lows[i]; previous_close=closes[i-1]
                if high <= 0 or low <= 0 or previous_close <= 0:
                    continue
                tr_sum+=max(high-low,abs(high-previous_close),abs(low-previous_close))
                tr_count+=1
            add("atr_14",tr_sum/tr_count if tr_count else None,bool(tr_count),"need valid OHLC history" if not tr_count else None)
        else:
            add("atr_14",None,False,"OHLC history unavailable")
        if orderbook is not None:
            age_ms=None
            if getattr(orderbook,"last_event_time_ms",0):
                age_ms=max(0,int(timestamp.timestamp()*1000)-int(orderbook.last_event_time_ms))
            fresh=bool(getattr(orderbook,"valid",False)) and age_ms is not None and age_ms <= 5000
            if fresh and orderbook.bids and orderbook.asks:
                best_bid=float(orderbook.bids[0].price); best_ask=float(orderbook.asks[0].price)
                mid=(best_bid+best_ask)/2.0; spread=best_ask-best_bid
                bid_depth=0.0
                for level in orderbook.bids: bid_depth+=float(level.size)
                ask_depth=0.0
                for level in orderbook.asks: ask_depth+=float(level.size)
                total_depth=bid_depth+ask_depth
                imbalance=(bid_depth-ask_depth)/total_depth if total_depth else None
                add("orderbook_mid",mid,True); add("orderbook_spread",spread,True)
                add("orderbook_imbalance",imbalance,imbalance is not None,"zero total depth" if imbalance is None else None)
            else:
                reason="orderbook unavailable"
                if getattr(orderbook,"valid",False) and age_ms is not None and age_ms > 5000: reason="orderbook stale"
                add("orderbook_mid",None,False,reason); add("orderbook_spread",None,False,reason); add("orderbook_imbalance",None,False,reason)
        return FeatureSnapshot(symbol,timestamp,tuple(values),self.version)
