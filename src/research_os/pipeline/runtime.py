from __future__ import annotations
import asyncio
from research_os.core.config import get_settings
from research_os.data.pipeline import IngestionPipeline
from research_os.notifications.telegram_client import TelegramClient
from research_os.pipeline.live import LiveSignalService
from research_os.pipeline.statistics_scheduler import StatisticsScheduler
from research_os.signals.guard import SignalGuard

async def run():
    settings=get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required for live runtime")
    telegram=TelegramClient(settings.telegram_bot_token,settings.telegram_chat_id)
    ingestion=IngestionPipeline()
    stop=asyncio.Event()
    guard=SignalGuard(max_latency_ms=settings.signal_guard_max_latency_ms,max_spread_bps=settings.signal_guard_max_spread_bps,max_orderbook_age_ms=settings.signal_guard_max_orderbook_age_ms,min_probability=settings.signal_min_probability,min_expected_value=settings.signal_min_ev)
    service=LiveSignalService(telegram=telegram,publisher=ingestion.publish,guard=guard)
    scheduler=StatisticsScheduler(telegram,settings.report_timezone,settings.report_hour,settings.report_minute)
    writer=asyncio.create_task(ingestion.run_writer(stop))
    try:
        await asyncio.gather(service.run(),scheduler.run())
    finally:
        stop.set()
        await ingestion.drain()
        await writer

def main():
    asyncio.run(run())
