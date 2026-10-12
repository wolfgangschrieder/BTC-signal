"""Restore only observed, confirmed, contiguous minute history before a decision."""
from datetime import timedelta
from math import isfinite

from sqlalchemy import text

from research_os.features.timeframes import OHLCVBar


def contiguous_suffix(rows, before):
    expected = before-timedelta(minutes=1)
    restored = []
    for row in rows:  # query supplies newest first
        if row['event_time']!=expected:
            break
        values = [float(row[name]) for name in ('open','high','low','close','volume')]
        opening,high,low,close,volume = values
        if not all(isfinite(value) for value in values) or min(opening,high,low,close)<=0 or volume<0:
            break
        if not low<=min(opening,close)<=max(opening,close)<=high:
            break
        restored.append(OHLCVBar(expected,opening,high,low,close,volume))
        expected -= timedelta(minutes=1)
    return list(reversed(restored))


def load_history(session, symbol, before, as_of, limit):
    if not 1<=limit<=10080:
        raise ValueError('History must be bounded to seven days')
    session.execute(text('SET TRANSACTION READ ONLY'))
    session.execute(text("SET LOCAL statement_timeout = '5s'"))
    rows = session.execute(text("""SELECT c.event_time,c.open,c.high,c.low,c.close,c.volume
        FROM market.candles c JOIN raw.events r ON r.id=c.raw_event_id
        WHERE c.symbol=:symbol AND c.interval='1' AND c.source='bybit'
        AND c.event_time>=:lower AND c.event_time<:before
        AND c.event_time + interval '1 minute'<=:as_of
        AND c.point_in_time_available_at<=:as_of AND r.point_in_time_available_at<=:as_of
        AND r.payload->>'confirm'='true'
        ORDER BY c.event_time DESC LIMIT :limit"""),
        {'symbol':symbol,'lower':before-timedelta(minutes=limit),'before':before,
         'as_of':as_of,'limit':limit}).mappings().all()
    return contiguous_suffix(rows,before)
