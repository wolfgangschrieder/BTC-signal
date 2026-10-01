from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


class BybitReconnectRequired(Exception):
    """Raised by a message handler when the current stream must be resynchronized."""


@dataclass(frozen=True)
class BybitWebSocketConfig:
    url: str = "wss://stream.bybit.com/v5/public/linear"
    ping_interval_seconds: float = 20.0
    ping_timeout_seconds: float = 10.0
    reconnect_initial_seconds: float = 1.0
    reconnect_max_seconds: float = 30.0
    receive_timeout_seconds: float = 45.0


class BybitWebSocket:
    """Resilient public Bybit WebSocket transport.

    The transport owns connection lifecycle and never exposes trading endpoints.
    Invalid JSON or malformed messages are isolated to the current message.
    """

    def __init__(
        self,
        topics: list[str],
        handler: MessageHandler,
        config: BybitWebSocketConfig | None = None,
    ) -> None:
        if not topics:
            raise ValueError("at least one subscription topic is required")
        self._topics = tuple(topics)
        self._handler = handler
        self._config = config or BybitWebSocketConfig()
        self._stop = asyncio.Event()

    async def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        delay = self._config.reconnect_initial_seconds
        while not self._stop.is_set():
            try:
                await self._run_connection()
                delay = self._config.reconnect_initial_seconds
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Bybit WebSocket connection failed; reconnecting")
                if self._stop.is_set():
                    break
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._config.reconnect_max_seconds)

    async def _run_connection(self) -> None:
        async with websockets.asyncio.client.connect(
            self._config.url,
            ping_interval=None,
            ping_timeout=self._config.ping_timeout_seconds,
            close_timeout=5,
        ) as websocket:
            await self._subscribe(websocket)
            ping_task = asyncio.create_task(self._application_ping_loop(websocket))
            try:
                while not self._stop.is_set():
                    try:
                        message = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=self._config.receive_timeout_seconds,
                        )
                    except asyncio.TimeoutError as exc:
                        raise ConnectionError("Bybit WebSocket receive timeout") from exc
                    await self._handle_message(message)
            finally:
                ping_task.cancel()
                await asyncio.gather(ping_task, return_exceptions=True)

    async def _application_ping_loop(self, websocket: ClientConnection) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(self._config.ping_interval_seconds)
            await websocket.send(json.dumps({"op": "ping"}))

    async def _subscribe(self, websocket: ClientConnection) -> None:
        payload = {"op": "subscribe", "args": list(self._topics)}
        await websocket.send(json.dumps(payload))

    async def _handle_message(self, message: str | bytes) -> None:
        try:
            decoded = json.loads(message)
        except (TypeError, json.JSONDecodeError):
            logger.warning("Ignoring malformed Bybit WebSocket JSON")
            return

        if not isinstance(decoded, dict):
            logger.warning("Ignoring non-object Bybit WebSocket message")
            return

        if decoded.get("op") in {"subscribe", "pong"}:
            if decoded.get("success") is False:
                logger.error("Bybit WebSocket operation failed: %s", decoded)
            return

        try:
            await self._handler(decoded)
        except BybitReconnectRequired:
            raise
        except Exception:
            logger.exception("WebSocket message handler failed; continuing")
