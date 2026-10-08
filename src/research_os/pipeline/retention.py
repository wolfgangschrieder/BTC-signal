"""Bound high-frequency storage; preserve candles and research results."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from research_os.database.session import SessionLocal

logger = logging.getLogger(__name__)
HIGH_FREQUENCY = ('trade', 'ticker', 'orderbook_update', 'orderbook_snapshot')
TABLES = ('trades', 'market_snapshots', 'orderbook_updates', 'orderbook_snapshots')


def prune_batch(session, cutoff: datetime, batch_size: int = 1000) -> int:
    """Caller owns the transaction; no unrelated data or research outputs are deleted."""
    if batch_size <= 0:
        raise ValueError('batch_size must be positive')
    session.execute(text("SET LOCAL statement_timeout = '15s'"))
    ids = list(session.execute(text("""
        SELECT id FROM raw.events
        WHERE source='bybit' AND event_type IN
            ('trade','ticker','orderbook_update','orderbook_snapshot')
          AND ingestion_time < :cutoff
        ORDER BY ingestion_time, id LIMIT :batch FOR UPDATE SKIP LOCKED
    """), {'cutoff': cutoff, 'batch': batch_size}).scalars())
    if not ids:
        return 0
    for table in TABLES:
        session.execute(text(f'DELETE FROM market.{table} WHERE raw_event_id = ANY(:ids)'), {'ids': ids})
    for table in ('funding_rates', 'open_interest'):
        session.execute(text(f'DELETE FROM derivatives.{table} WHERE raw_event_id = ANY(:ids)'), {'ids': ids})
    session.execute(text('DELETE FROM raw.event_fingerprints WHERE event_id = ANY(:ids)'), {'ids': ids})
    session.execute(text('DELETE FROM raw.events WHERE id = ANY(:ids)'), {'ids': ids})
    return len(ids)


class RetentionScheduler:
    def __init__(self, hours: int, interval_seconds: float = 60):
        if hours <= 0 or interval_seconds <= 0:
            raise ValueError('retention hours and interval must be positive')
        self.hours = hours
        self.interval_seconds = interval_seconds

    def _prune(self):
        cutoff = datetime.now(UTC) - timedelta(hours=self.hours)
        count = 0
        # Limit each pass and commit each batch, avoiding long transactions.
        for _ in range(20):
            with SessionLocal() as session:
                deleted = prune_batch(session, cutoff)
                session.commit()
            count += deleted
            if deleted < 1000:
                break
        if count:
            logger.warning('Retention removed %s high-frequency events older than %sh', count, self.hours)

    async def run(self, stop: asyncio.Event):
        while not stop.is_set():
            try:
                await asyncio.to_thread(self._prune)
            except Exception as error:  # noqa: BLE001 - retry database failures next cycle
                logger.error('Retention failed (%s); retrying next cycle', type(error).__name__)
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass
