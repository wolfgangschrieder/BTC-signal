"""Resolve research outcomes independently of Telegram reporting."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from research_os.database.session import SessionLocal
from research_os.signals.outcome_evaluator import SignalOutcomeEvaluator

logger = logging.getLogger(__name__)


class OutcomeResolutionScheduler:
    def __init__(self, interval_seconds: float = 60):
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.interval_seconds = interval_seconds
        self.evaluator = SignalOutcomeEvaluator()

    def _resolve(self) -> int:
        with SessionLocal() as session:
            return self.evaluator.resolve_pending(session, datetime.now(UTC))

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await asyncio.to_thread(self._resolve)
            except Exception as error:  # noqa: BLE001 - keep the periodic worker alive after DB failures
                logger.error(
                    "Outcome resolution failed (%s); retrying next cycle", type(error).__name__
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass
