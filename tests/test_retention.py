import asyncio
import os
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from sqlalchemy import text

from research_os.data.models import EventType, RawEvent
from research_os.data.raw_store import RawEventStore
from research_os.database.session import SessionLocal
from research_os.pipeline.retention import RetentionScheduler, prune_batch


@pytest.mark.skipif(not os.getenv('DATABASE_URL'), reason='requires migrated PostgreSQL')
def test_retention_deletes_related_rows_but_preserves_recent_and_candles():
    now = datetime.now(UTC)
    old = now - timedelta(hours=8)
    with SessionLocal() as session:
        try:
            ids = []
            for event_type, timestamp in [(EventType.TRADE, old), (EventType.TRADE, now), (EventType.CANDLE, old)]:
                event = RawEvent(source='bybit', symbol='RETENTIONTEST', event_type=event_type,
                                 event_time=timestamp, ingestion_time=timestamp,
                                 point_in_time_available_at=timestamp, payload={})
                ids.append(RawEventStore().append(session, event))
            session.execute(text("INSERT INTO raw.event_fingerprints VALUES (:fp,:id)"),
                            {'fp': 'retention-test-fingerprint', 'id': ids[0]})
            session.execute(text("""INSERT INTO market.trades
                (event_time,ingestion_time,point_in_time_available_at,symbol,source,raw_event_id,price,size,side)
                VALUES (:ts,:ts,:ts,'RETENTIONTEST','bybit',:id,100,1,'buy')"""), {'ts': old, 'id': ids[0]})
            for table, field in [('funding_rates', 'funding_rate'), ('open_interest', 'open_interest')]:
                session.execute(text(f"""INSERT INTO derivatives.{table}
                    (event_time,ingestion_time,point_in_time_available_at,symbol,source,raw_event_id,{field})
                    VALUES (:ts,:ts,:ts,'RETENTIONTEST','bybit',:id,1)"""), {'ts': old, 'id': ids[0]})
            assert prune_batch(session, now-timedelta(hours=6)) >= 1
            for table in ('funding_rates', 'open_interest'):
                assert session.execute(text(f'SELECT count(*) FROM derivatives.{table} WHERE raw_event_id=:id'),
                                       {'id': ids[0]}).scalar() == 0
            remaining = set(session.execute(text('SELECT id FROM raw.events WHERE id = ANY(:ids)'), {'ids': ids}).scalars())
            assert remaining == set(ids[1:])
            assert session.execute(text('SELECT count(*) FROM market.trades WHERE raw_event_id=:id'), {'id': ids[0]}).scalar() == 0
            assert session.execute(text('SELECT count(*) FROM raw.event_fingerprints WHERE event_id=:id'), {'id': ids[0]}).scalar() == 0
            assert prune_batch(session, now-timedelta(hours=6)) == 0
        finally:
            session.rollback()


@pytest.mark.asyncio
async def test_retention_runs_off_thread_and_stops_promptly(monkeypatch):
    stop = asyncio.Event()
    called = Event()
    scheduler = RetentionScheduler(6, interval_seconds=3600)
    monkeypatch.setattr(scheduler, '_prune', called.set)
    task = asyncio.create_task(scheduler.run(stop))
    assert await asyncio.to_thread(called.wait, 1)
    stop.set()
    await asyncio.wait_for(task, 1)


def test_invalid_retention_rejected():
    with pytest.raises(ValueError):
        RetentionScheduler(0)
