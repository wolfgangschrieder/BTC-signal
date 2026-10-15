import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from research_os.pipeline.history import contiguous_suffix, load_history
from research_os.pipeline.live import LiveSignalService

BEFORE = datetime(2026,10,13,0,0,tzinfo=UTC)


def row(minutes, **changes):
    return {'event_time':BEFORE-timedelta(minutes=minutes),'open':100,'high':102,
            'low':99,'close':101,'volume':1,**changes}


def test_missing_or_invalid_bar_truncates_to_contiguous_suffix():
    assert len(contiguous_suffix([row(1),row(2),row(4)],BEFORE))==2
    assert not contiguous_suffix([row(2)],BEFORE)
    assert not contiguous_suffix([row(1,close=float('nan'))],BEFORE)
    assert not contiguous_suffix([row(1,high=100)],BEFORE)
    assert [bar.timestamp for bar in contiguous_suffix([row(1),row(2)],BEFORE)]==[row(2)['event_time'],row(1)['event_time']]


def test_query_is_bounded_read_only_confirmed_and_point_in_time():
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value=[row(1)]
    assert len(load_history(session,'BTCUSDT',BEFORE,BEFORE,10080))==1
    sql = '\n'.join(str(call.args[0]) for call in session.execute.call_args_list)
    assert 'READ ONLY' in sql and "confirm'='true'" in sql
    assert 'c.point_in_time_available_at<=:as_of' in sql and 'r.point_in_time_available_at<=:as_of' in sql
    assert 'LIMIT :limit' in sql and 'interval' in sql
    with pytest.raises(ValueError):
        load_history(session,'BTCUSDT',BEFORE,BEFORE,10081)


@pytest.mark.asyncio
async def test_restore_rebuilds_all_price_buffers_without_signals_or_orderflow(monkeypatch):
    service = LiveSignalService(publisher=lambda event:None)
    bars = contiguous_suffix([row(1),row(2)],BEFORE)
    monkeypatch.setattr(service,'_load_price_history',lambda *args:bars)
    await service._restore_price_history(BEFORE)
    assert list(service.closes)==[101,101] and len(service.bars_1m)==2
    assert service._last_candle_start==bars[-1].timestamp
    assert service.cumulative_delta==0 and not service.trades
    assert not service._history_restore_pending
    service._reset_stream_state()
    assert service._history_restore_pending and not service.bars_1m


@pytest.mark.asyncio
async def test_live_gap_and_late_candle_do_not_join_discontinuous_prices():
    service = LiveSignalService()
    async def candle(when):
        timestamp = int(when.timestamp()*1000)
        await service._handle({'topic':'kline.1.BTCUSDT','ts':timestamp+60000,
            'data':[{'interval':'1','start':timestamp,'open':'100','high':'102','low':'99',
                     'close':'101','volume':'1','confirm':True}]})
    await candle(BEFORE)
    await candle(BEFORE+timedelta(minutes=1))
    assert len(service.bars_1m)==2
    await candle(BEFORE)
    assert len(service.bars_1m)==2
    await candle(BEFORE+timedelta(minutes=3))
    assert len(service.bars_1m)==1 and service._previous_candle_flow_price is None


@pytest.mark.asyncio
async def test_restore_failure_does_not_fabricate_history(monkeypatch):
    service = LiveSignalService(publisher=lambda event:None)
    def failed(*args):
        raise RuntimeError('offline')
    monkeypatch.setattr(service,'_load_price_history',failed)
    await service._restore_price_history(BEFORE)
    assert not service.closes and service._last_candle_start is None


@pytest.mark.skipif(not os.getenv('DATABASE_URL'),reason='requires migrated PostgreSQL')
def test_real_database_excludes_unconfirmed_and_late_available_bars():
    from research_os.data.models import EventType, RawEvent
    from research_os.data.raw_store import RawEventStore
    from research_os.database.session import SessionLocal
    from research_os.market.store import NormalizedMarketDataStore
    symbol = 'HIST'+uuid4().hex[:12]
    with SessionLocal() as session:
        for minute in (3,2,1):
            data = row(minute)
            event = RawEvent(source='bybit',event_type=EventType.CANDLE,symbol=symbol,
                event_time=data['event_time'],ingestion_time=BEFORE,
                point_in_time_available_at=BEFORE,
                payload={'interval':'1','confirm':minute!=1,**{k:v for k,v in data.items() if k!='event_time'}})
            identity = RawEventStore().append(session,event)
            NormalizedMarketDataStore().persist(session,event,identity)
        session.flush()
        # Caller sees only committed/pre-existing rows in a normal restoration read.
        session.commit()
    try:
        with SessionLocal() as session:
            assert load_history(session,symbol,BEFORE,BEFORE,10)==[]
        with SessionLocal() as session:
            assert len(load_history(session,symbol,BEFORE-timedelta(minutes=1),BEFORE,10))==2
        with SessionLocal() as session:
            assert load_history(session,symbol,BEFORE-timedelta(minutes=1),BEFORE-timedelta(seconds=1),10)==[]
    finally:
        from sqlalchemy import text
        with SessionLocal() as session:
            session.execute(text('DELETE FROM market.candles WHERE symbol=:symbol'),{'symbol':symbol})
            session.execute(text('DELETE FROM raw.events WHERE symbol=:symbol'),{'symbol':symbol})
            session.commit()


def test_restoration_diagnostic_distinguishes_gap_raw_loss_and_invalid_prices():
    from research_os.pipeline.history import describe_history
    def stored(minute, **changes):
        return row(minute,raw_present=True,eligible=True,**changes)
    diagnostic = describe_history([stored(1),stored(2),stored(4)],BEFORE)
    assert diagnostic['restorable_contiguous_minutes']==2
    assert diagnostic['boundary_reason']=='no_stored_bar_at_boundary'
    rows = [stored(1),row(2,raw_present=False,eligible=False),stored(3)]
    diagnostic = describe_history(rows,BEFORE)
    assert diagnostic['eligible_rows']==2 and diagnostic['raw_missing_rows']==1
    assert diagnostic['restorable_contiguous_minutes']==1
    assert diagnostic['boundary_reason']=='raw_confirmation_unavailable'
    diagnostic = describe_history([stored(1,close=float('nan'))],BEFORE)
    assert diagnostic['boundary_reason']=='invalid_ohlcv'
    assert diagnostic['restorable_contiguous_minutes']==0


def test_restoration_diagnostic_counts_only_complete_utc_timeframes():
    from research_os.pipeline.history import describe_history
    rows = [row(i,raw_present=True,eligible=True) for i in range(1,481)]
    result = describe_history(rows,BEFORE)
    assert result['complete_restorable_bars']=={'1h':8,'4h':2,'1d':0}
    assert result['boundary_reason']=='end_of_scanned_history'
