from __future__ import annotations
from datetime import datetime
from math import log
from collections.abc import Sequence
from .models import FeatureSnapshot, FeatureValue


class FeatureEngine:
    """Pure, deterministic features. Missing inputs remain unavailable; never fabricated."""
    version = "features-v1"

    def build(
        self,
        symbol: str,
        timestamp: datetime,
        closes: Sequence[float],
        volumes: Sequence[float] = (),
        highs: Sequence[float] = (),
        lows: Sequence[float] = (),
        orderbook=None,
    ) -> FeatureSnapshot:
        """Build deterministic features with bounded allocations for the live hot path."""
        values: list[FeatureValue] = []
        n = len(closes)

        if n >= 2 and closes[-2] > 0 and closes[-1] > 0:
            ratio = closes[-1] / closes[-2]
            values.append(FeatureValue("return_1", ratio - 1.0, True, "derived", timestamp))
            values.append(FeatureValue("log_return_1", log(ratio), True, "derived", timestamp))
        else:
            reason = "need at least 2 positive closes"
            values.append(FeatureValue("return_1", None, False, "derived", timestamp, reason))
            values.append(FeatureValue("log_return_1", None, False, "derived", timestamp, reason))

        if n >= 6:
            base = closes[-6]
            valid_base = base > 0 and closes[-1] > 0
            values.append(FeatureValue(
                "return_5",
                (closes[-1] / base) - 1.0 if valid_base else None,
                valid_base,
                "derived",
                timestamp,
                None if valid_base else "non-positive base",
            ))
        else:
            values.append(FeatureValue("return_5", None, False, "derived", timestamp, "need at least 6 closes"))

        if n >= 2:
            count = 0
            mean_return = 0.0
            m2 = 0.0
            prev = closes[0]
            for close in closes[1:]:
                if prev > 0 and close > 0:
                    value = (close / prev) - 1.0
                    count += 1
                    delta = value - mean_return
                    mean_return += delta / count
                    m2 += delta * (value - mean_return)
                prev = close
            available = count >= 2
            values.append(FeatureValue(
                "realized_vol",
                (m2 / count) ** 0.5 if available else None,
                available,
                "derived",
                timestamp,
                None if available else "need at least 2 returns",
            ))
        else:
            values.append(FeatureValue("realized_vol", None, False, "derived", timestamp, "need at least 2 closes"))

        if volumes:
            total_volume = 0.0
            for volume in volumes:
                total_volume += volume
            values.append(FeatureValue("volume_mean", total_volume / len(volumes), True, "derived", timestamp))
        else:
            values.append(FeatureValue("volume_mean", None, False, "derived", timestamp, "volume unavailable"))

        if n >= 2 and len(highs) == n and len(lows) == n:
            tr_sum = 0.0
            tr_count = 0
            start = max(1, n - 14)
            for i in range(start, n):
                high = highs[i]
                low = lows[i]
                previous_close = closes[i - 1]
                if high <= 0 or low <= 0 or previous_close <= 0:
                    continue
                tr_sum += max(
                    high - low,
                    abs(high - previous_close),
                    abs(low - previous_close),
                )
                tr_count += 1
            values.append(FeatureValue(
                "atr_14",
                tr_sum / tr_count if tr_count else None,
                bool(tr_count),
                "derived",
                timestamp,
                None if tr_count else "need valid OHLC history",
            ))
        else:
            values.append(FeatureValue("atr_14", None, False, "derived", timestamp, "OHLC history unavailable"))

        if orderbook is not None:
            event_ms = getattr(orderbook, "last_event_time_ms", 0)
            age_ms = None
            if event_ms:
                age_ms = max(0, int(timestamp.timestamp() * 1000) - int(event_ms))
            fresh = bool(getattr(orderbook, "valid", False)) and age_ms is not None and age_ms <= 5000
            if fresh and orderbook.bids and orderbook.asks:
                best_bid = float(orderbook.bids[0].price)
                best_ask = float(orderbook.asks[0].price)
                mid = (best_bid + best_ask) / 2.0
                spread = best_ask - best_bid
                bid_depth = 0.0
                for level in orderbook.bids:
                    bid_depth += float(level.size)
                ask_depth = 0.0
                for level in orderbook.asks:
                    ask_depth += float(level.size)
                total_depth = bid_depth + ask_depth
                imbalance = (bid_depth - ask_depth) / total_depth if total_depth else None
                values.append(FeatureValue("orderbook_mid", mid, True, "derived", timestamp))
                values.append(FeatureValue("orderbook_spread", spread, True, "derived", timestamp))
                values.append(FeatureValue(
                    "orderbook_imbalance",
                    imbalance,
                    imbalance is not None,
                    "derived",
                    timestamp,
                    "zero total depth" if imbalance is None else None,
                ))
            else:
                reason = "orderbook unavailable"
                if getattr(orderbook, "valid", False) and age_ms is not None and age_ms > 5000:
                    reason = "orderbook stale"
                values.append(FeatureValue("orderbook_mid", None, False, "derived", timestamp, reason))
                values.append(FeatureValue("orderbook_spread", None, False, "derived", timestamp, reason))
                values.append(FeatureValue("orderbook_imbalance", None, False, "derived", timestamp, reason))

        return FeatureSnapshot(symbol, timestamp, tuple(values), self.version)
