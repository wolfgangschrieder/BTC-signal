import pytest
from datetime import datetime, timezone
from research_os.cross_market.ingestion import CrossMarketIngestionService
from research_os.cross_market.models import CrossMarketObservation

class FakeProvider:
    async def fetch_series(self,asset,series_id,observation_start=None,observation_end=None):
        return [CrossMarketObservation(
            asset,datetime(2026,1,1,tzinfo=timezone.utc),
            datetime(2026,1,2,tzinfo=timezone.utc),100.0,f"fake:{series_id}"
        )]

class FakeRepository:
    def __init__(self): self.saved=[]
    def save(self,session,observation): self.saved.append(observation)

@pytest.mark.asyncio
async def test_ingestion_persists_selected_assets():
    repo=FakeRepository()
    service=CrossMarketIngestionService(FakeProvider(),repo)
    total=await service.fetch_and_store(object(),assets=("SPX","VIX"))
    assert total==2
    assert [x.asset for x in repo.saved]==["SPX","VIX"]
