"""Bounded REST gap repair; historical data becomes available only on receipt."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from research_os.data.models import EventType, RawEvent
from research_os.data.raw_store import RawEventStore
from research_os.database.session import SessionLocal
from research_os.market.models import Candle


def normalize_page(payload, symbol, before, received):
    result = payload["result"]
    if result["symbol"] != symbol or result["category"] != "linear":
        raise ValueError("Unexpected REST candle market")
    events = {}
    for row in result["list"]:
        start = int(row[0])
        when = datetime.fromtimestamp(start / 1000, timezone.utc)
        if start % 60000 or when >= before or when + timedelta(minutes=1) > received:
            continue
        opening, high, low, close, volume, turnover = map(Decimal, row[1:7])
        if (not all(v.is_finite() for v in (opening, high, low, close, volume, turnover))
                or min(opening, high, low, close) <= 0 or min(volume, turnover) < 0
                or not low <= min(opening, close) <= max(opening, close) <= high):
            raise ValueError("Invalid REST OHLCV")
        events[when] = RawEvent(source="bybit", event_type=EventType.CANDLE, symbol=symbol,
            event_time=when, ingestion_time=received, point_in_time_available_at=received,
            payload={"symbol": symbol, "interval": "1", "confirm": True,
                     "open": str(opening), "high": str(high), "low": str(low),
                     "close": str(close), "volume": str(volume), "turnover": str(turnover),
                     "recovery_source": "rest"})
    return sorted(events.values(), key=lambda event: event.event_time)


def persist_missing(events):
    inserted = 0
    with SessionLocal() as session:
        for event in events:
            # ON CONFLICT protects against another writer inserting
            # between the existence check and the insert.
            if session.scalar(select(Candle.symbol).where(Candle.symbol == event.symbol,
                    Candle.interval == "1", Candle.event_time == event.event_time)):
                continue
            identity = RawEventStore().append(session, event)
            p = event.payload
            statement = insert(Candle).values(symbol=event.symbol, interval="1",
                event_time=event.event_time, ingestion_time=event.ingestion_time,
                point_in_time_available_at=event.point_in_time_available_at,
                source="bybit", raw_event_id=identity,
                **{name: Decimal(p[name]) for name in
                   ("open", "high", "low", "close", "volume", "turnover")}
            ).on_conflict_do_nothing(index_elements=["symbol", "interval", "event_time"])
            inserted += int(session.execute(statement.returning(Candle.event_time)).scalar_one_or_none() is not None)
        session.commit()
    return inserted


async def recover_history(rest, symbol, before, limit, persist=persist_missing):
    import asyncio
    lower = before - timedelta(minutes=limit)
    cursor = int(before.timestamp() * 1000) - 1
    inserted = 0
    # At most eleven requests for a seven-day window. Never create decisions here.
    for _ in range((limit + 999) // 1000):
        payload = await rest.get_kline(symbol=symbol, interval="1", limit=1000, end=cursor)
        received = datetime.now(timezone.utc)
        events = normalize_page(payload, symbol, before, received)
        if not events:
            break
        oldest = events[0].event_time
        next_cursor = int(oldest.timestamp() * 1000) - 1
        if next_cursor >= cursor:
            raise ValueError("REST pagination did not advance")
        selected = [event for event in events if event.event_time >= lower]
        inserted += await asyncio.to_thread(persist, selected)
        if oldest <= lower:
            break
        cursor = next_cursor
    return inserted
