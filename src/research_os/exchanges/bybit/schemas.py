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

class BybitTicker(BaseModel):
    symbol: str
    last_price: Decimal = Field(gt=0)
    bid_price: Decimal | None = Field(default=None, gt=0)
    ask_price: Decimal | None = Field(default=None, gt=0)
    timestamp_ms: int = Field(gt=0)
