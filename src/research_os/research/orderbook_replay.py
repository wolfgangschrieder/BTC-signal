from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Any
from research_os.exchanges.bybit.orderbook import OrderBook, OrderBookState

@dataclass(frozen=True)
class HistoricalOrderBookEvent:
    event_time: datetime
    point_in_time_available_at: datetime
    message: Mapping[str, Any]

    def is_pit_valid(self, decision_time: datetime) -> bool:
        return self.point_in_time_available_at <= decision_time and self.event_time <= decision_time

def replay_to(events: Iterable[HistoricalOrderBookEvent], decision_time: datetime,
              symbol: str, max_levels: int = 50) -> OrderBookState | None:
    if decision_time.tzinfo is None:
        raise ValueError("decision_time must be timezone-aware")
    book=OrderBook(symbol, max_levels=max_levels)
    ordered=sorted((e for e in events if e.is_pit_valid(decision_time)),
                   key=lambda e: (e.event_time, e.message.get("data",{}).get("u",0)))
    for event in ordered:
        book.apply(dict(event.message))
    state=book.state
    return state if state.valid else None

def replay_many(events: Iterable[HistoricalOrderBookEvent], decision_times: Iterable[datetime],
                symbol: str, max_levels: int = 50) -> tuple[tuple[datetime,OrderBookState], ...]:
    cached=tuple(events)
    result=[]
    for decision_time in sorted(decision_times):
        state=replay_to(cached, decision_time, symbol, max_levels)
        if state is not None:
            result.append((decision_time,state))
    return tuple(result)
