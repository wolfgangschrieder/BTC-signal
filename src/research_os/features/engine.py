from __future__ import annotations
from datetime import datetime
from math import log
from statistics import mean, pstdev
from collections.abc import Sequence
from .models import FeatureSnapshot, FeatureValue

class FeatureEngine:
    """Pure, deterministic features. Missing inputs remain unavailable; never fabricated."""
    version = "features-v1"

    def build(self, symbol: str, timestamp: datetime, closes: Sequence[float], volumes: Sequence[float] = (), highs: Sequence[float] = (), lows: Sequence[float] = (), orderbook=None) -> FeatureSnapshot:
        values: list[FeatureValue] = []
        def add(name, value, available=True, reason=None):
            values.append(FeatureValue(name, value, available, "derived", timestamp, reason))
        if len(closes) >= 2 and closes[-2] > 0:
            add("return_1", (closes[-1] / closes[-2]) - 1)
            add("log_return_1", log(closes[-1] / closes[-2]))
        else:
            add("return_1", None, False, "need at least 2 positive closes")
        if len(closes) >= 6:
            base=closes[-6]
            add("return_5", (closes[-1] / base)-1 if base > 0 else None, base > 0, "non-positive base" if base <= 0 else None)
        else:
            add("return_5", None, False, "need at least 6 closes")
        if len(closes) >= 2:
            returns=[(closes[i]/closes[i-1])-1 for i in range(1,len(closes)) if closes[i-1]>0]
            add("realized_vol", pstdev(returns) if len(returns)>=2 else None, len(returns)>=2, "need at least 2 returns")
        else: add("realized_vol", None, False, "need at least 2 closes")
        if volumes:
            add("volume_mean", mean(volumes), True)
        else:
            add("volume_mean", None, False, "volume unavailable")
        if len(closes) >= 2 and len(highs) == len(closes) and len(lows) == len(closes):
            true_ranges = []
            for i in range(1, len(closes)):
                if highs[i] <= 0 or lows[i] <= 0 or closes[i - 1] <= 0:
                    continue
                true_ranges.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
            period = min(14, len(true_ranges))
            add("atr_14", mean(true_ranges[-period:]) if period else None, bool(period), "need valid OHLC history")
        else:
            add("atr_14", None, False, "OHLC history unavailable")
        return FeatureSnapshot(symbol, timestamp, tuple(values), self.version)
