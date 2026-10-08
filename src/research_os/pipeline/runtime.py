from __future__ import annotations

import asyncio
import logging
import sys

from research_os.core.config import get_settings
from research_os.data.pipeline import IngestionPipeline
from research_os.notifications.telegram_client import TelegramClient
from research_os.pipeline.live import LiveSignalService
from research_os.pipeline.retention import RetentionScheduler
from research_os.pipeline.outcome_scheduler import OutcomeResolutionScheduler
from research_os.pipeline.statistics_scheduler import StatisticsScheduler
from research_os.pipeline.storage import StorageBudget
from research_os.signals.guard import SignalGuard


async def run():
    settings = get_settings()
    notifications_enabled = getattr(settings, "signal_emission_enabled", True)
    if notifications_enabled and (not settings.telegram_bot_token or not settings.telegram_chat_id):
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required for live runtime")
    telegram = (
        TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id)
        if notifications_enabled
        else None
    )
    storage = None
    if getattr(settings, "storage_path", ""):
        storage = StorageBudget(settings.storage_path, settings.storage_max_database_gb,
                                settings.storage_min_free_gb)
        await asyncio.to_thread(storage.check)
    ingestion = IngestionPipeline(storage_budget=storage) if storage else IngestionPipeline()
    stop = asyncio.Event()
    guard = SignalGuard(
        max_latency_ms=settings.signal_guard_max_latency_ms,
        max_spread_bps=settings.signal_guard_max_spread_bps,
        max_orderbook_age_ms=settings.signal_guard_max_orderbook_age_ms,
        min_probability=settings.signal_min_probability,
        min_expected_value=settings.signal_min_ev,
    )
    service = LiveSignalService(telegram=telegram, publisher=ingestion.publish, guard=guard, settings=settings)
    scheduler = StatisticsScheduler(
        telegram, settings.report_timezone, settings.report_hour, settings.report_minute
    )
    writer = asyncio.create_task(ingestion.run_writer(stop), name="ingestion-writer")
    live = asyncio.create_task(service.run(), name="live-service")
    statistics = asyncio.create_task(
        scheduler.run(stop) if telegram is not None else stop.wait(), name="statistics-scheduler"
    )
    outcomes = asyncio.create_task(OutcomeResolutionScheduler().run(stop), name="outcome-resolver")
    retention_hours = getattr(settings, "raw_retention_hours", 0)
    retention = asyncio.create_task(
        RetentionScheduler(retention_hours).run(stop) if retention_hours else stop.wait(),
        name="retention",
    )
    storage_task = asyncio.create_task(
        storage.run(stop) if storage else stop.wait(), name="storage-budget"
    )
    tasks = (writer, live, statistics, outcomes, retention, storage_task)
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        # Propagate background failures immediately, rather than leaving live running.
        for task in tasks:
            if task in done:
                task.result()
    finally:
        propagating_error = sys.exc_info()[0] is not None
        shutdown_timed_out = False
        await service.stop()
        # Stop producers before asking the ingestion writer to drain and exit.
        statistics.cancel()
        outcomes.cancel()
        retention.cancel()
        storage_task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(live), timeout=10)
        except TimeoutError:
            shutdown_timed_out = True
        except Exception:
            # The initiating task failure is propagated by the supervisor above.
            logging.getLogger(__name__).exception("Live service failed during shutdown")
        finally:
            stop.set()
            for task in (live, statistics, outcomes, retention, storage_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(live, statistics, outcomes, retention, storage_task, return_exceptions=True)
            try:
                await asyncio.wait_for(asyncio.shield(writer), timeout=10)
            except TimeoutError:
                shutdown_timed_out = True
            except Exception:
                logging.getLogger(__name__).exception("Ingestion writer failed during shutdown")
                if not propagating_error:
                    raise
            finally:
                if not writer.done():
                    writer.cancel()
                await asyncio.gather(writer, return_exceptions=True)
        if shutdown_timed_out:
            if not propagating_error:
                raise RuntimeError("Live runtime shutdown timed out")
            logging.getLogger(__name__).error("Live runtime shutdown timed out")


def main():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("research_os.pipeline.realtime").setLevel(logging.INFO)
    asyncio.run(run())
