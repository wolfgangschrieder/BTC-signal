from __future__ import annotations
from datetime import datetime
from .providers import FREDProvider, DEFAULT_FRED_SERIES
from .repository import CrossMarketRepository

class CrossMarketIngestionService:
    def __init__(self,provider:FREDProvider,repository:CrossMarketRepository|None=None):
        self.provider=provider
        self.repository=repository or CrossMarketRepository()

    async def fetch_and_store(self,session,start=None,end=None,assets=None):
        selected=assets or tuple(DEFAULT_FRED_SERIES)
        total=0
        for asset in selected:
            series_id=DEFAULT_FRED_SERIES.get(asset)
            if series_id is None:
                raise ValueError(f"unknown FRED cross-market asset: {asset}")
            observations=await self.provider.fetch_series(
                asset,series_id,
                observation_start=start.date().isoformat() if start else None,
                observation_end=end.date().isoformat() if end else None,
            )
            for observation in observations:
                self.repository.save(session,observation)
            total+=len(observations)
        return total
