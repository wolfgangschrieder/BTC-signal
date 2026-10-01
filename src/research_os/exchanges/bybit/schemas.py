from datetime import datetime, timezone
from decimal import Decimal
from pydantic import BaseModel, Field

class BybitTrade(BaseModel):
    symbol: str
    price: Decimal = Field(gt=0)
    size: Decimal = Field(gt=0)
    side: str
    timestamp_ms: int = Field(gt=0)
    def event_time(self): return datetime.fromtimestamp(self.timestamp_ms/1000,tz=timezone.utc)

class BybitOrderBookMessage(BaseModel):
    symbol: str
    update_id: int = Field(ge=0)
    sequence: int|None = Field(default=None,ge=0)
    timestamp_ms: int = Field(gt=0)
    bids: list[tuple[Decimal,Decimal]] = Field(default_factory=list)
    asks: list[tuple[Decimal,Decimal]] = Field(default_factory=list)

class BybitTicker(BaseModel):
    symbol: str
    last_price: Decimal = Field(gt=0)
    bid_price: Decimal|None = Field(default=None,gt=0)
    ask_price: Decimal|None = Field(default=None,gt=0)
    timestamp_ms: int = Field(gt=0)

class BybitKline(BaseModel):
    symbol: str
    interval: str
    start_ms: int = Field(gt=0)
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(ge=0)
    turnover: Decimal|None = Field(default=None,ge=0)
    confirm: bool = False
    timestamp_ms: int = Field(gt=0)
    def event_time(self): return datetime.fromtimestamp(self.start_ms/1000,tz=timezone.utc)
