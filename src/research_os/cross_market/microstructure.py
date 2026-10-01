from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from statistics import mean, pstdev
from typing import Sequence

@dataclass(frozen=True, slots=True)
class BookLevel:
    price: float
    size: float

@dataclass(frozen=True, slots=True)
class ExchangeOrderBook:
    exchange: str
    timestamp_ms: int
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]

@dataclass(frozen=True, slots=True)
class OFIObservation:
    exchange: str
    timestamp_ms: int
    raw_ofi: float
    normalized_ofi: float | None
    levels: int = 5

@dataclass(frozen=True, slots=True)
class LeadLagResult:
    leader: str
    follower: str
    lag_ms: int
    correlation: float | None
    observations: int

@dataclass(frozen=True, slots=True)
class CrossExchangeOFIAggregate:
    value: float | None
    exchanges: tuple[str, ...]
    coverage: int
    dispersion: float | None
    available: bool

SUPPORTED_OFI_EXCHANGES = ("binance", "bybit", "coinbase")

def order_flow_imbalance(previous: ExchangeOrderBook | None, current: ExchangeOrderBook, levels: int = 5) -> float | None:
    if levels <= 0:
        raise ValueError("levels must be positive")
    if previous is None:
        return None
    if previous.exchange != current.exchange:
        raise ValueError("previous/current exchange mismatch")
    if len(previous.bids) < levels or len(previous.asks) < levels or len(current.bids) < levels or len(current.asks) < levels:
        return None
    total = 0.0
    for i in range(levels):
        pb, cb = previous.bids[i], current.bids[i]
        pa, ca = previous.asks[i], current.asks[i]
        if cb.price >= pb.price:
            total += cb.size
        if cb.price <= pb.price:
            total -= pb.size
        if ca.price <= pa.price:
            total -= ca.size
        if ca.price >= pa.price:
            total += pa.size
    return total

class RollingOFIZScore:
    __slots__ = ("window", "min_samples", "_history")
    def __init__(self, window: int = 300, min_samples: int = 30) -> None:
        if window <= 0 or min_samples <= 1 or min_samples > window:
            raise ValueError("invalid rolling z-score configuration")
        self.window = window
        self.min_samples = min_samples
        self._history: list[float] = []
    def transform(self, value: float | None) -> float | None:
        if value is None:
            return None
        if len(self._history) < self.min_samples:
            self._history.append(value)
            if len(self._history) > self.window:
                self._history.pop(0)
            return None
        sigma = pstdev(self._history)
        z = (value - mean(self._history)) / sigma if sigma > 0.0 else 0.0
        self._history.append(value)
        if len(self._history) > self.window:
            self._history.pop(0)
        return z

def normalize_multi_exchange_ofi(
    observations: Sequence[OFIObservation],
    normalizers: dict[str, RollingOFIZScore],
) -> tuple[OFIObservation, ...]:
    """Normalize each exchange independently before cross-exchange comparison."""
    result = []
    for item in observations:
        normalizer = normalizers.get(item.exchange)
        normalized = normalizer.transform(item.raw_ofi) if normalizer is not None else None
        result.append(
            OFIObservation(
                item.exchange,
                item.timestamp_ms,
                item.raw_ofi,
                normalized,
                item.levels,
            )
        )
    return tuple(result)

def normalized_multi_exchange_ofi(observations: Sequence[OFIObservation]) -> dict[str, float]:
    return {item.exchange: item.normalized_ofi for item in observations if item.normalized_ofi is not None}

def aggregate_normalized_multi_exchange_ofi(
    observations: Sequence[OFIObservation],
    min_exchanges: int = 2,
) -> CrossExchangeOFIAggregate:
    if min_exchanges < 1:
        raise ValueError("min_exchanges must be positive")
    normalized = normalized_multi_exchange_ofi(observations)
    exchanges = tuple(sorted(normalized))
    if len(exchanges) < min_exchanges:
        return CrossExchangeOFIAggregate(None, exchanges, len(exchanges), None, False)
    values = [normalized[exchange] for exchange in exchanges]
    mean_value = mean(values)
    dispersion = mean((value - mean_value) ** 2 for value in values) ** 0.5
    return CrossExchangeOFIAggregate(mean_value, exchanges, len(exchanges), dispersion, True)

def pearson_lead_lag(leader_values: Sequence[float], follower_values: Sequence[float], lag_steps: int) -> float | None:
    if lag_steps < 0:
        raise ValueError("lag_steps must be non-negative")
    n = min(len(leader_values), len(follower_values) - lag_steps)
    if n < 2:
        return None
    x = leader_values[:n]
    y = follower_values[lag_steps:lag_steps + n]
    mx, my = mean(x), mean(y)
    dx = [v - mx for v in x]
    dy = [v - my for v in y]
    denom = sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    return sum(a * b for a, b in zip(dx, dy)) / denom if denom > 0.0 else 0.0

DEFAULT_LEAD_LAG_LAGS_MS = (1000, 5000, 15000, 30000, 60000, 300000)

def lead_lag_scan(leader_values: Sequence[float], follower_values: Sequence[float], step_ms: int, lags_ms: Sequence[int] = DEFAULT_LEAD_LAG_LAGS_MS) -> tuple[LeadLagResult, ...]:
    if step_ms <= 0:
        raise ValueError("step_ms must be positive")
    results = []
    for lag_ms in lags_ms:
        if lag_ms < 0:
            raise ValueError("lag must be non-negative")
        steps = lag_ms // step_ms
        results.append(LeadLagResult("leader", "follower", lag_ms, pearson_lead_lag(leader_values, follower_values, steps), max(0, min(len(leader_values), len(follower_values) - steps))))
    return tuple(results)
