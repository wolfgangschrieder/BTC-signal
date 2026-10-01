from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field

class BybitTrade(BaseModel):
    symbol: str
    price: Decimal = Field(gt=0)
    size: Decimal = Field(gt=0)
    side: str
    timestamp_ms: int = Field(gt=0)

    def event_time(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp_ms / 1000, tz=__import__("datetime").timezone.utc)

class BybitOrderBookMessage(BaseModel):
    symbol: str
    update_id: int = Field(ge=0)
    sequence: int | None = Field(default=None, ge=0)
    timestamp_ms: int = Field(gt=0)
    bids: list[tuple[Decimal, Decimal]] = Field(default_factory=list)
    asks: list[tuple[Decimal, Decimal]] = Field(default_factory=list)

class BybitTicker(BaseModel):
    symbol: str
    last_price: Decimal = Field(gt=0)
    bid_price: Decimal | None = Field(default=None, gt=0)
    ask_price: Decimal | None = Field(default=None, gt=0)
    timestamp_ms: int = Field(gt=0)
