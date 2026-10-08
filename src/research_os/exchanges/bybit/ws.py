from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from research_os.pipeline.latency import LatencyTelemetry

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
        latency: LatencyTelemetry | None = None,
        on_disconnect: Callable[[], None] | None = None,
    ) -> None:
        if not topics:
            raise ValueError("at least one subscription topic is required")
        self._on_disconnect = on_disconnect
        self._connection = None
        self._pong = asyncio.Event()
        self._topics = tuple(topics)
        self._handler = handler
        self._config = config or BybitWebSocketConfig()
        self._latency = latency
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
        if self._connection is not None:
            await self._connection.close()

    async def run(self) -> None:
        delay = self._config.reconnect_initial_seconds
        while not self._stop.is_set():
            notified = False
            try:
                await self._run_connection()
                delay = self._config.reconnect_initial_seconds
            except asyncio.CancelledError:
                raise
            except Exception:
                if self._on_disconnect is not None:
                    self._on_disconnect()
                    notified = True
                logger.exception("Bybit WebSocket connection failed; reconnecting")
                if self._stop.is_set():
                    break
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except TimeoutError:
                    pass
                delay = min(delay * 2, self._config.reconnect_max_seconds)
            finally:
                self._last_latency_ms = None
                self._last_latency_at = None
                self._ping_sent_monotonic = None
                if not notified and self._on_disconnect is not None:
                    self._on_disconnect()

    async def _run_connection(self) -> None:
        async with websockets.asyncio.client.connect(
            self._config.url,
            ping_interval=None,
            ping_timeout=self._config.ping_timeout_seconds,
            close_timeout=5,
        ) as websocket:
            self._connection = websocket
            self._last_latency_ms = None
            self._last_latency_at = None
            await self._subscribe(websocket)
            ping_task = asyncio.create_task(self._application_ping_loop(websocket))
            try:
                while not self._stop.is_set():
                    try:
                        receive_started = time.perf_counter()
                        receive = asyncio.create_task(websocket.recv())
                        try:
                            done, _ = await asyncio.wait(
                                (receive, ping_task),
                                timeout=self._config.receive_timeout_seconds,
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                            if ping_task in done:
                                ping_task.result()
                                raise ConnectionError("Bybit ping loop stopped")
                            if receive not in done:
                                raise TimeoutError
                            message = receive.result()
                        finally:
                            if not receive.done():
                                receive.cancel()
                            await asyncio.gather(receive, return_exceptions=True)
                        if self._latency is not None:
                            self._latency.observe(
                                "ws_receive",
                                (time.perf_counter() - receive_started) * 1000.0,
                            )
                    except TimeoutError as exc:
                        raise ConnectionError("Bybit WebSocket receive timeout") from exc
                    await self._handle_message(message)
            finally:
                self._connection = None
                ping_task.cancel()
                await asyncio.gather(ping_task, return_exceptions=True)

    async def _application_ping_loop(self, websocket: ClientConnection) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(self._config.ping_interval_seconds)
            self._pong.clear()
            self._ping_sent_monotonic = time.monotonic()
            await websocket.send(json.dumps({"op": "ping"}))
            try:
                await asyncio.wait_for(self._pong.wait(), timeout=self._config.ping_timeout_seconds)
            except TimeoutError as exc:
                raise ConnectionError("Bybit application pong timeout") from exc

    async def _subscribe(self, websocket: ClientConnection) -> None:
        payload = {"op": "subscribe", "args": list(self._topics)}
        await websocket.send(json.dumps(payload))

    async def _handle_message(self, message: str | bytes) -> None:
        try:
            decode_started = time.perf_counter()
            decoded = json.loads(message)
            if self._latency is not None:
                self._latency.observe(
                    "ws_decode",
                    (time.perf_counter() - decode_started) * 1000.0,
                )
        except (TypeError, json.JSONDecodeError):
            logger.warning("Ignoring malformed Bybit WebSocket JSON")
            return

        if not isinstance(decoded, dict):
            logger.warning("Ignoring non-object Bybit WebSocket message")
            return

        if decoded.get("op") == "pong" or (
            decoded.get("op") == "ping"
            and decoded.get("ret_msg") == "pong"
            and decoded.get("success") is True
        ):
            if self._ping_sent_monotonic is not None:
                self._last_latency_ms = (time.monotonic() - self._ping_sent_monotonic) * 1000.0
                self._last_latency_at = datetime.now(UTC)
                self._ping_sent_monotonic = None
                self._pong.set()
            return

        if decoded.get("op") == "subscribe":
            if decoded.get("success") is False:
                raise BybitReconnectRequired("Bybit rejected subscription")
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
            if self._latency is not None:
                self._latency.observe("ws_handler", duration_ms)
            self._max_handler_duration_ms = max(self._max_handler_duration_ms, duration_ms)
            self._messages_processed += 1
            self._handler_started_monotonic = None
