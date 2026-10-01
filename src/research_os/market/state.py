from datetime import datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field

class MarketStructure(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGE = "range"
    TRANSITION = "transition"
    UNKNOWN = "unknown"

class DataQualityState(BaseModel):
    overall_score: float = Field(ge=0.0, le=1.0)
    pit_valid: bool
    orderbook_valid: bool
    missing_ratio: float = Field(ge=0.0, le=1.0)
    stale_ratio: float = Field(ge=0.0, le=1.0)

class MarketStateVector(BaseModel):
    """Versioned, reproducible fingerprint of market state; never a signal."""

    state_id: str
    symbol: str
    timestamp: datetime
    decision_time: datetime
    point_in_time_available_at: datetime
    vector_version: str = "1.0"
    feature_version: str
    factor_version: str
    regime_version: str
    code_version: str
    vector: dict[str, float | int | None]
    market_state: MarketStructure
    data_quality: DataQualityState
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
