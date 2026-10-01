from __future__ import annotations
import asyncio
from research_os.core.config import get_settings
from research_os.notifications.telegram_client import TelegramClient
from research_os.pipeline.live import LiveSignalService
from research_os.pipeline.statistics_scheduler import StatisticsScheduler

async def run():
    settings=get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required for live runtime")
    telegram=TelegramClient(settings.telegram_bot_token,settings.telegram_chat_id)
    service=LiveSignalService(telegram=telegram)
    scheduler=StatisticsScheduler(telegram,settings.report_timezone,settings.report_hour,settings.report_minute)
    await asyncio.gather(service.run(),scheduler.run())

def main(): asyncio.run(run())
