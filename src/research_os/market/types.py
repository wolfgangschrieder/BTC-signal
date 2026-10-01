from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

class MarketStructure(StrEnum):
    BULLISH="bullish"
    BEARISH="bearish"
    RANGE="range"
    TRANSITION="transition"
    UNKNOWN="unknown"

class OrderSide(StrEnum):
    BUY="buy"
    SELL="sell"

@dataclass(slots=True, frozen=True)
class TradeEvent:
    symbol: str
    event_time: datetime
    point_in_time_available_at: datetime
    price: float
    quantity: float
    side: OrderSide
    exchange: str="bybit"

@dataclass(slots=True, frozen=True)
class BookLevel:
    price: float
    quantity: float

@dataclass(slots=True, frozen=True)
class OrderbookState:
    symbol: str
    timestamp: datetime
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    valid: bool=True
    sequence: int|None=None
    exchange: str="bybit"

    @property
    def best_bid(self) -> float|None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float|None:
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> float|None:
        bid, ask=self.best_bid, self.best_ask
        return (bid+ask)/2 if bid is not None and ask is not None else None

    @property
    def spread(self) -> float|None:
        bid, ask=self.best_bid, self.best_ask
        return ask-bid if bid is not None and ask is not None else None

@dataclass(slots=True, frozen=True)
class OrderflowState:
    timestamp: datetime
    buy_volume: float
    sell_volume: float
    delta: float
    cumulative_delta: float|None=None
    trade_count: int=0
    large_trade_share: float|None=None

@dataclass(slots=True, frozen=True)
class CrossMarketObservation:
    asset: str
    timestamp: datetime
    point_in_time_available_at: datetime
    value: float
    source: str
    unit: str="raw"

@dataclass(slots=True, frozen=True)
class CrossMarketOrderflow:
    exchange: str
    symbol: str
    timestamp: datetime
    ofi: float
    levels: int=5
    valid: bool=True
