from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field


class BybitTrade(BaseModel):
    symbol: str = Field(validation_alias=AliasChoices("symbol", "s"))
    price: Decimal = Field(gt=0, validation_alias=AliasChoices("price", "p"))
    size: Decimal = Field(gt=0, validation_alias=AliasChoices("size", "v"))
    side: Literal["Buy", "Sell"] = Field(validation_alias=AliasChoices("side", "S"))
    timestamp_ms: int = Field(gt=0, validation_alias=AliasChoices("timestamp_ms", "T"))
    trade_id: str | None = Field(default=None, validation_alias=AliasChoices("trade_id", "i", "execId"))

    def event_time(self):
        return datetime.fromtimestamp(self.timestamp_ms / 1000, tz=UTC)

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
    funding_rate: Decimal|None = None
    open_interest: Decimal|None = Field(default=None,ge=0)
    next_funding_time_ms: int|None = Field(default=None,gt=0)
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
    def event_time(self): return datetime.fromtimestamp(self.start_ms/1000,tz=UTC)
