from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime

from research_os.data.ingestion import EventIngestionService
from research_os.data.models import QualityEvent, RawEvent
from research_os.database.session import SessionLocal
from research_os.market.store import NormalizedMarketDataStore


class IngestionPipeline:
    """Async boundary between realtime producers and synchronous DB writes."""

    def __init__(
        self,
        ingestion: EventIngestionService | None = None,
        max_queue_size: int = 10_000,
    ) -> None:
        self._failure: Exception | None = None
        self._failed = asyncio.Event()
        self.ingestion = ingestion or EventIngestionService()
        self.normalized_store = NormalizedMarketDataStore()
        self.queue: asyncio.Queue[RawEvent] = asyncio.Queue(maxsize=max_queue_size)
        self.quality_events: asyncio.Queue[QualityEvent] = asyncio.Queue()

    async def publish(self, event: RawEvent) -> None:
        if self._failure is not None:
            raise RuntimeError("ingestion writer failed") from self._failure
        await self._until_failure(self.queue.put(event))

    async def run_writer(self, stop: asyncio.Event) -> None:
        while not stop.is_set() or not self.queue.empty():
            try:
                event = await asyncio.wait_for(self.queue.get(), timeout=0.5)
            except TimeoutError:
                continue
            try:
                await asyncio.to_thread(self._persist_one, event)
            except Exception as exc:
                self._failure = exc
                self._failed.set()
                raise
            finally:
                self.queue.task_done()

    def _persist_one(self, event: RawEvent) -> None:
        with SessionLocal() as session:
            try:
                event_id, _ = self.ingestion.ingest(session, event)
                if event_id is not None:
                    self.normalized_store.persist(session, event, event_id)
                session.commit()
            except Exception:
                session.rollback()
                raise

    async def _until_failure(self, operation) -> None:
        work = asyncio.create_task(operation)
        failed = asyncio.create_task(self._failed.wait())
        try:
            await asyncio.wait((work, failed), return_when=asyncio.FIRST_COMPLETED)
            if self._failure is not None:
                raise RuntimeError("ingestion writer failed") from self._failure
            await work
        finally:
            for task in (work, failed):
                if not task.done():
                    task.cancel()
            await asyncio.gather(work, failed, return_exceptions=True)

    async def drain(self) -> None:
        await self._until_failure(self.queue.join())

    async def publish_many(self, events: Iterable[RawEvent]) -> None:
        for event in events:
            await self.publish(event)

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(UTC)
