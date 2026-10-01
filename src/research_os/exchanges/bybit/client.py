from typing import Any
import httpx

class BybitRestClient:
    BASE_URL = "https://api.bybit.com"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def get_orderbook(self, category: str = "linear", symbol: str = "BTCUSDT", limit: int = 50) -> dict[str, Any]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(base_url=self.BASE_URL, timeout=10.0)
        try:
            response = await client.get("/v5/market/orderbook", params={"category": category, "symbol": symbol, "limit": limit})
            response.raise_for_status()
            payload = response.json()
            if payload.get("retCode") != 0:
                raise RuntimeError(f"Bybit API error: {payload.get('retCode')}: {payload.get('retMsg')}")
            return payload
        finally:
            if owns_client:
                await client.aclose()

    async def get_kline(self, category: str = "linear", symbol: str = "BTCUSDT", interval: str = "1", limit: int = 200) -> dict[str, Any]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(base_url=self.BASE_URL, timeout=10.0)
        try:
            response = await client.get("/v5/market/kline", params={"category": category, "symbol": symbol, "interval": interval, "limit": limit})
            response.raise_for_status()
            payload = response.json()
            if payload.get("retCode") != 0:
                raise RuntimeError(f"Bybit API error: {payload.get('retCode')}: {payload.get('retMsg')}")
            return payload
        finally:
            if owns_client:
                await client.aclose()

    async def get_tickers(self, category: str = "linear", symbol: str = "BTCUSDT") -> dict[str, Any]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(base_url=self.BASE_URL, timeout=10.0)
        try:
            response = await client.get("/v5/market/tickers", params={"category": category, "symbol": symbol})
            response.raise_for_status()
            payload = response.json()
            if payload.get("retCode") != 0:
                raise RuntimeError(f"Bybit API error: {payload.get('retCode')}: {payload.get('retMsg')}")
            return payload
        finally:
            if owns_client:
                await client.aclose()
