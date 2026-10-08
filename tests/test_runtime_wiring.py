import asyncio

import pytest

from research_os.data.pipeline import IngestionPipeline
from research_os.pipeline.live import LiveSignalService


def test_live_service_accepts_publisher():
    service = LiveSignalService(publisher=IngestionPipeline().publish)
    assert service.publisher is not None


def test_ingestion_pipeline_queue_is_bounded():
    pipeline = IngestionPipeline(max_queue_size=2)
    assert pipeline.queue.maxsize == 2


async def _run_runtime_with_writer_failure(monkeypatch, notifications_enabled):
    from types import SimpleNamespace

    import pytest

    from research_os.pipeline import runtime

    started = asyncio.Event()
    stopped = asyncio.Event()
    scheduler_stopped = asyncio.Event()

    class Pipeline:
        async def publish(self, event):
            pass

        async def run_writer(self, stop):
            await started.wait()
            raise RuntimeError("database outage")

    class Service:
        def __init__(self, **kwargs):
            if not notifications_enabled:
                assert kwargs["telegram"] is None

        async def run(self):
            started.set()
            await stopped.wait()

        async def stop(self):
            stopped.set()

    class Scheduler:
        def __init__(self, *args):
            pass

        async def run(self, stop):
            try:
                await stop.wait()
            finally:
                scheduler_stopped.set()

    settings = SimpleNamespace(
        telegram_bot_token="test" if notifications_enabled else "",
        telegram_chat_id="test" if notifications_enabled else "",
        signal_emission_enabled=notifications_enabled,
        signal_guard_max_latency_ms=500,
        signal_guard_max_spread_bps=10,
        signal_guard_max_orderbook_age_ms=5000,
        signal_min_probability=0.7,
        signal_min_ev=0,
        report_timezone="Europe/Moscow",
        report_hour=20,
        report_minute=0,
    )
    monkeypatch.setattr(runtime, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime, "IngestionPipeline", Pipeline)
    monkeypatch.setattr(runtime, "LiveSignalService", Service)
    monkeypatch.setattr(runtime, "StatisticsScheduler", Scheduler)
    with pytest.raises(RuntimeError, match="database outage"):
        await asyncio.wait_for(runtime.run(), timeout=1)
    assert stopped.is_set()
    assert scheduler_stopped.is_set() == notifications_enabled


@pytest.mark.parametrize("notifications_enabled", [True, False])
def test_runtime_stops_live_and_scheduler_when_writer_fails(monkeypatch, notifications_enabled):
    asyncio.run(_run_runtime_with_writer_failure(monkeypatch, notifications_enabled))
