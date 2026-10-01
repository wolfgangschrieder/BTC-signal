from __future__ import annotations
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Callable, Awaitable
import websockets
from research_os.execution.reconciliation import RemoteOrderState
from research_os.execution.service import ExecutionStatus

@dataclass(frozen=True)
class BybitPrivateWSConfig:
    api_key: str
    api_secret: str
    testnet: bool=True
    max_active_time: str|None=None

class BybitPrivateOrderStream:
    """Authenticated Bybit private order stream. Read-only: it only consumes order events."""
    topic="order"

    def __init__(self, config: BybitPrivateWSConfig):
        if not config.api_key or not config.api_secret:
            raise ValueError("Bybit API credentials are required")
        self.config=config
        base="wss://stream-testnet.bybit.com/v5/private" if config.testnet else "wss://stream.bybit.com/v5/private"
        self.url=base + (f"?max_active_time={config.max_active_time}" if config.max_active_time else "")

    @staticmethod
    def _auth_args(api_key: str, api_secret: str, expires: int) -> list[str]:
        signature=hmac.new(api_secret.encode(),f"GET/realtime{expires}".encode(),hashlib.sha256).hexdigest()
        return [api_key,expires,signature]

    @staticmethod
    def parse_message(message: str) -> list[RemoteOrderState]:
        payload=json.loads(message)
        states=[]
        for item in payload.get("data",[]):
            status={
                "New":ExecutionStatus.SUBMITTED,
                "PartiallyFilled":ExecutionStatus.PARTIALLY_FILLED,
                "Filled":ExecutionStatus.FILLED,
                "Cancelled":ExecutionStatus.CANCELLED,
                "Rejected":ExecutionStatus.REJECTED,
                "Deactivated":ExecutionStatus.REJECTED,
            }.get(item.get("orderStatus"))
            if status is None or not item.get("orderLinkId"):
                continue
            states.append(RemoteOrderState(
                item["orderLinkId"],status,item.get("orderId"),
                item.get("rejectReason") or item.get("cancelType"),
            ))
        return states

    async def run(self, on_state: Callable[[RemoteOrderState], Awaitable[None]], stop: asyncio.Event | None=None):
        import asyncio
        stop=stop or asyncio.Event()
        backoff=1.0
        while not stop.is_set():
            try:
                async with websockets.connect(self.url,ping_interval=20,ping_timeout=45) as ws:
                    expires=int((time.time()+1)*1000)
                    await ws.send(json.dumps({"op":"auth","args":self._auth_args(self.config.api_key,self.config.api_secret,expires)}))
                    auth=json.loads(await ws.recv())
                    if not auth.get("success"):
                        raise RuntimeError(f"Bybit private WS auth failed: {auth}")
                    await ws.send(json.dumps({"op":"subscribe","args":[self.topic]}))
                    sub=json.loads(await ws.recv())
                    if sub.get("success") is False:
                        raise RuntimeError(f"Bybit private WS subscription failed: {sub}")
                    backoff=1.0
                    while not stop.is_set():
                        raw=await ws.recv()
                        for state in self.parse_message(raw):
                            await on_state(state)
            except asyncio.CancelledError:
                raise
            except Exception:
                if stop.is_set():
                    break
                await asyncio.sleep(backoff)
                backoff=min(backoff*2,30.0)
