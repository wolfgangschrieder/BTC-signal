from datetime import datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field

class EventType(StrEnum):
    TRADE = "trade"
    TICKER = "ticker"
    CANDLE = "candle"
    ORDERBOOK_UPDATE = "orderbook_update"
    ORDERBOOK_SNAPSHOT = "orderbook_snapshot"
    FUNDING = "funding"
    OPEN_INTEREST = "open_interest"
    LIQUIDATION = "liquidation"

class RawEvent(BaseModel):
    source: str
    event_type: EventType
    symbol: str | None = None
    event_time: datetime
    ingestion_time: datetime
    point_in_time_available_at: datetime
    payload: dict[str, Any]
    schema_version: str = "1.0"

    def is_pit_valid(self, decision_time: datetime) -> bool:
        return self.point_in_time_available_at <= decision_time

class QualityCode(StrEnum):
    OK = "ok"
    MISSING = "missing"
    DUPLICATE = "duplicate"
    TIMESTAMP_INVALID = "timestamp_invalid"
    OUT_OF_ORDER = "out_of_order"
    STALE = "stale"
    IMPOSSIBLE_VALUE = "impossible_value"
    MALFORMED = "malformed"
    PIT_VIOLATION = "pit_violation"
    ORDERBOOK_GAP = "orderbook_gap"

class QualityEvent(BaseModel):
    code: QualityCode
    severity: str = "warning"
    source: str
    event_time: datetime | None = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
