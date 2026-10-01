from __future__ import annotations
from dataclasses import dataclass
from research_os.market.types import BookLevel, OrderbookState

@dataclass(slots=True, frozen=True)
class LiquidityState:
    timestamp: object
    valid: bool
    bid_depth: float
    ask_depth: float
    imbalance: float
    spread: float|None

class LiquidityEngine:
    __slots__=("levels",)
    def __init__(self, levels: int=5):
        if levels <= 0: raise ValueError("levels must be positive")
        self.levels=levels

    def calculate(self, book: OrderbookState) -> LiquidityState:
        if not book.valid:
            return LiquidityState(book.timestamp,False,0.0,0.0,0.0,book.spread)
        bids=book.bids[:self.levels]; asks=book.asks[:self.levels]
        bid=sum(x.quantity for x in bids if x.quantity >= 0)
        ask=sum(x.quantity for x in asks if x.quantity >= 0)
        total=bid+ask
        return LiquidityState(book.timestamp,True,bid,ask,(bid-ask)/total if total else 0.0,book.spread)
