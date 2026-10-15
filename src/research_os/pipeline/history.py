"""Restore only observed, confirmed, contiguous minute history before a decision."""
from datetime import timedelta
from math import isfinite

from sqlalchemy import text

from research_os.features.timeframes import OHLCVBar, Timeframe, aggregate_bars


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


def history_diagnostic(session, symbol, before, as_of, limit):
    """Measure the restoration path, including retained candles without raw proof.

    This is not a measurement of a running worker's in-memory buffer.
    """
    if not 1<=limit<=10080:
        raise ValueError('History must be bounded to seven days')
    rows = session.execute(text("""SELECT c.event_time,c.open,c.high,c.low,c.close,c.volume,
            r.id IS NOT NULL AS raw_present,
            coalesce(r.point_in_time_available_at<=:as_of AND r.payload->>'confirm'='true',false) AS eligible
        FROM market.candles c LEFT JOIN raw.events r ON r.id=c.raw_event_id
        WHERE c.symbol=:symbol AND c.interval='1' AND c.source='bybit'
          AND c.event_time>=:lower AND c.event_time<:before
          AND c.event_time + interval '1 minute'<=:as_of
          AND c.point_in_time_available_at<=:as_of
        ORDER BY c.event_time DESC LIMIT :limit"""),
        {'symbol':symbol,'lower':before-timedelta(minutes=limit),'before':before,
         'as_of':as_of,'limit':limit}).mappings().all()
    return describe_history(rows, before)


def describe_history(rows, before):
    eligible = [row for row in rows if row['eligible']]
    restored = contiguous_suffix(eligible,before)
    expected = before-timedelta(minutes=len(restored)+1)
    blocked = next((row for row in rows if row['event_time']==expected),None)
    if restored and len(restored)==len(rows):
        reason = 'end_of_scanned_history'
    elif blocked is None:
        reason = 'no_stored_bar_at_boundary'
    elif not blocked['raw_present']:
        reason = 'raw_confirmation_unavailable'
    elif not blocked['eligible']:
        reason = 'not_confirmed_or_raw_not_available_at_cutoff'
    else:
        reason = 'invalid_ohlcv'
    return {'complete_restorable_bars':{str(tf):len(aggregate_bars(restored,tf))
                                          for tf in (Timeframe.H1,Timeframe.H4,Timeframe.D1)},
            'stored_rows':len(rows), 'raw_missing_rows':sum(not row['raw_present'] for row in rows),
            'eligible_rows':len(eligible), 'restorable_contiguous_minutes':len(restored),
            'first_restorable_utc':restored[0].timestamp.isoformat() if restored else None,
            'boundary_utc':expected.isoformat(), 'boundary_reason':reason,
            'scope':'Database restoration at cutoff; not live in-memory history. Raw absence does not prove retention caused it.'}
