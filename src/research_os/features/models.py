from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

@dataclass(frozen=True)
class FeatureValue:
    name: str
    value: float | None
    available: bool
    source: str
    timestamp: datetime
    reason: str | None = None

@dataclass(frozen=True)
class FeatureSnapshot:
    symbol: str
    timestamp: datetime
    features: tuple[FeatureValue, ...] = field(default_factory=tuple)
    version: str = "features-v1"
