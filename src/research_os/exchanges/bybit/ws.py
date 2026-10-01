from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
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
        self._ping_sent_monotonic: float | None = None
        self._last_latency_ms: float | None = None
        self._last_latency_at: datetime | None = None
        self._messages_processed = 0
        self._handler_errors = 0
        self._last_handler_duration_ms: float | None = None
        self._max_handler_duration_ms: float = 0.0
        self._handler_started_monotonic: float | None = None

    @property
    def latency_ms(self) -> float | None:
        return self._last_latency_ms

    @property
    def latency_at(self) -> datetime | None:
        return self._last_latency_at

    @property
    def messages_processed(self) -> int:
        return self._messages_processed

    @property
    def handler_errors(self) -> int:
        return self._handler_errors

    @property
    def last_handler_duration_ms(self) -> float | None:
        return self._last_handler_duration_ms

    @property
    def max_handler_duration_ms(self) -> float:
        return self._max_handler_duration_ms

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
            self._ping_sent_monotonic = time.monotonic()
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

        if decoded.get("op") == "pong":
            if self._ping_sent_monotonic is not None:
                self._last_latency_ms = (time.monotonic() - self._ping_sent_monotonic) * 1000.0
                self._last_latency_at = datetime.now(timezone.utc)
                self._ping_sent_monotonic = None
            return

        if decoded.get("op") == "subscribe":
            if decoded.get("success") is False:
                logger.error("Bybit WebSocket operation failed: %s", decoded)
            return

        started = time.monotonic()
        self._handler_started_monotonic = started
        try:
            await self._handler(decoded)
        except BybitReconnectRequired:
            raise
        except Exception:
            self._handler_errors += 1
            logger.exception("WebSocket message handler failed; continuing")
        finally:
            duration_ms = (time.monotonic() - started) * 1000.0
            self._last_handler_duration_ms = duration_ms
            self._max_handler_duration_ms = max(self._max_handler_duration_ms, duration_ms)
            self._messages_processed += 1
            self._handler_started_monotonic = None
