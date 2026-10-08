"""Fail closed before ingestion when the PostgreSQL volume loses its reserve."""
from __future__ import annotations

import asyncio
import logging
import shutil

from sqlalchemy import text

from research_os.database.session import SessionLocal

GB = 1_000_000_000
logger = logging.getLogger(__name__)


class StorageBudget:
    def __init__(self, path: str, max_database_gb: float, min_free_gb: float,
                 interval_seconds: float = 10):
        if not path or min(max_database_gb, min_free_gb, interval_seconds) <= 0:
            raise ValueError('Storage path and positive limits are required')
        self.path = path
        self.max_bytes = max_database_gb * GB
        self.reserve_bytes = min_free_gb * GB
        self.interval_seconds = interval_seconds
        self.blocked = True

    def check(self):
        # Unknown storage state must never authorize ingestion.
        try:
            free = shutil.disk_usage(self.path).free
            with SessionLocal() as session:
                session.execute(text("SET LOCAL statement_timeout = '5s'"))
                size = session.execute(text('SELECT pg_database_size(current_database())')).scalar_one()
        except Exception:
            self.blocked = True
            raise
        if free < self.reserve_bytes or size >= self.max_bytes:
            self.blocked = True
            raise RuntimeError(
                f'Storage budget exceeded: database={size / GB:.2f} GB, '
                f'volume free={free / GB:.2f} GB; ingestion stopped'
            )
        self.blocked = False

    def require_writable(self):
        if self.blocked:
            raise RuntimeError('Storage budget unavailable; ingestion blocked')

    async def run(self, stop: asyncio.Event):
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                try:
                    await asyncio.to_thread(self.check)
                except Exception:
                    logger.error('Storage check failed; stopping live runtime')
                    raise
