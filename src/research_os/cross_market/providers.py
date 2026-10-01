from __future__ import annotations
from datetime import datetime, timezone
from math import isfinite
import httpx
from .models import CrossMarketObservation

FRED_URL="https://api.stlouisfed.org/fred/series/observations"

class CrossMarketProviderError(RuntimeError):
    pass

class FREDProvider:
    """Read-only FRED adapter with conservative acquisition-time PIT semantics."""
    source="fred"

    def __init__(self,api_key,timeout=10.0):
        if not api_key:
            raise ValueError("FRED API key is required")
        self.api_key=api_key
        self.timeout=timeout

    async def fetch_series(self,asset,series_id,observation_start=None,observation_end=None):
        params={"series_id":series_id,"api_key":self.api_key,"file_type":"json","sort_order":"asc"}
        if observation_start: params["observation_start"]=observation_start
        if observation_end: params["observation_end"]=observation_end
        fetched_at=datetime.now(timezone.utc)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response=await client.get(FRED_URL,params=params)
                response.raise_for_status()
                payload=response.json()
        except (httpx.HTTPError,ValueError) as exc:
            raise CrossMarketProviderError(f"FRED request failed for {series_id}") from exc
        observations=[]
        for item in payload.get("observations",[]):
            raw=item.get("value")
            if raw in (None,"."):
                continue
            try:
                value=float(raw)
                event_time=datetime.fromisoformat(item["date"]).replace(tzinfo=timezone.utc)
            except (TypeError,ValueError,KeyError) as exc:
                raise CrossMarketProviderError(f"invalid FRED observation for {series_id}") from exc
            if not isfinite(value):
                continue
            observations.append(CrossMarketObservation(
                asset=asset,timestamp=event_time,
                point_in_time_available_at=fetched_at,value=value,
                source=f"{self.source}:{series_id}",unit="index",
                payload={"series_id":series_id,
                         "realtime_start":item.get("realtime_start"),
                         "realtime_end":item.get("realtime_end")},
            ))
        return observations

DEFAULT_FRED_SERIES={
    "DOLLAR_BROAD":"DTWEXBGS",
    "SPX":"SP500",
    "NASDAQ":"NASDAQCOM",
    "VIX":"VIXCLS",
    "US10Y":"DGS10",
}
