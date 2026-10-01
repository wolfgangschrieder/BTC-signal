from __future__ import annotations
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import urlencode
import httpx
from research_os.execution.adapter import ExecutionAdapter, AdapterOrderResult, AdapterOrderStatus
from research_os.execution.order_intent import OrderIntent
from research_os.execution.reconciliation import RemoteOrderState
from research_os.execution.service import ExecutionStatus

@dataclass(frozen=True)
class BybitReadonlyConfig:
    api_key: str
    api_secret: str
    testnet: bool = True
    recv_window_ms: int = 5000
    timeout_seconds: float = 5.0

class BybitReadonlyAdapter(ExecutionAdapter):
    """Private Bybit V5 read-only adapter. It never creates, amends, or cancels orders."""
    name = "bybit-readonly"
    endpoint_path = "/v5/order/realtime"

    def __init__(self, config: BybitReadonlyConfig, client: httpx.Client | None = None):
        if not config.api_key or not config.api_secret:
            raise ValueError("Bybit API credentials are required")
        if config.recv_window_ms <= 0:
            raise ValueError("recv_window_ms must be positive")
        self.config = config
        self.base_url = "https://api-testnet.bybit.com" if config.testnet else "https://api.bybit.com"
        self.client = client or httpx.Client(timeout=config.timeout_seconds)

    def submit(self, intent: OrderIntent) -> AdapterOrderResult:
        raise RuntimeError("BybitReadonlyAdapter cannot submit orders")

    def _signed_get(self, params: dict[str, str]) -> dict:
        timestamp = str(int(time.time() * 1000))
        query = urlencode(sorted(params.items()))
        payload = timestamp + self.config.api_key + str(self.config.recv_window_ms) + query
        signature = hmac.new(self.config.api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        response = self.client.get(
            self.base_url + self.endpoint_path,
            params=params,
            headers={
                "X-BAPI-API-KEY": self.config.api_key,
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": str(self.config.recv_window_ms),
                "X-BAPI-SIGN": signature,
            },
        )
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error {data.get('retCode')}: {data.get('retMsg')}")
        return data

    @staticmethod
    def _map_status(value: str) -> ExecutionStatus:
        mapping = {
            "New": ExecutionStatus.SUBMITTED,
            "PartiallyFilled": ExecutionStatus.PARTIALLY_FILLED,
            "Filled": ExecutionStatus.FILLED,
            "Cancelled": ExecutionStatus.CANCELLED,
            "Rejected": ExecutionStatus.REJECTED,
            "Deactivated": ExecutionStatus.REJECTED,
        }
        if value not in mapping:
            raise ValueError(f"unsupported Bybit order status: {value}")
        return mapping[value]

    def get_order(self, client_order_id: str, symbol: str = "BTCUSDT") -> RemoteOrderState | None:
        data = self._signed_get({
            "category": "linear",
            "symbol": symbol,
            "orderLinkId": client_order_id,
            "openOnly": "0",
            "limit": "1",
        })
        items = data.get("result", {}).get("list", [])
        if not items:
            return None
        item = items[0]
        return RemoteOrderState(
            client_order_id=item.get("orderLinkId") or client_order_id,
            status=self._map_status(item["orderStatus"]),
            exchange_order_id=item.get("orderId"),
            reason=item.get("rejectReason") or item.get("cancelType"),
        )

    def close(self) -> None:
        self.client.close()
