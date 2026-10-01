import asyncio
from research_os.data.pipeline import IngestionPipeline
from research_os.pipeline.live import LiveSignalService

def test_live_service_accepts_publisher():
    service=LiveSignalService(publisher=IngestionPipeline().publish)
    assert service.publisher is not None

def test_ingestion_pipeline_queue_is_bounded():
    pipeline=IngestionPipeline(max_queue_size=2)
    assert pipeline.queue.maxsize==2
