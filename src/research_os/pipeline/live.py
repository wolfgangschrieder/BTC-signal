from __future__ import annotations
from collections import deque
from collections.abc import Awaitable,Callable
from datetime import datetime,timezone
import asyncio
from research_os.exchanges.bybit.normalizer import BybitNormalizer
from research_os.exchanges.bybit.orderbook import OrderBook, OrderBookError
from research_os.exchanges.bybit.client import BybitRestClient
from research_os.exchanges.bybit.ws import BybitWebSocket,BybitWebSocketConfig
from research_os.market.state_builder import MarketStateBuilder
from research_os.features.engine import FeatureEngine
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.probability import ProbabilityEngine
from research_os.notifications.telegram import TelegramFormatter
from research_os.notifications.telegram_client import TelegramClient
from research_os.signals.engine import SignalEngine
from research_os.signals.guard import SignalGuard
from research_os.signals.outcomes import SignalOutcome,OutcomeStatus
from research_os.signals.outcome_repository import SignalOutcomeRepository
from research_os.pipeline.realtime import RealtimeSignalPipeline
from research_os.database.session import SessionLocal
from research_os.market.state_repository import MarketStateRepository

EventPublisher=Callable[[object],Awaitable[None]]

class LiveSignalService:
    """Read-only Bybit live loop with validated orderbook recovery."""

    ORDERBOOK_STALE_MS=5000

    def __init__(self,symbol="BTCUSDT",interval="1",publisher:EventPublisher|None=None,telegram:TelegramClient|None=None,config=None):
        self.symbol=symbol; self.interval=interval; self.publisher=publisher
        self.telegram=telegram
        self.closes=deque(maxlen=200); self.highs=deque(maxlen=200); self.lows=deque(maxlen=200)
        self._last_candle_start=None
        self.orderbook=OrderBook(symbol,max_levels=50)
        self.rest=BybitRestClient()
        self._last_orderbook_update=datetime.min.replace(tzinfo=timezone.utc)
        self._recovery_lock=asyncio.Lock()
        self.features=FeatureEngine(); self.builder=MarketStateBuilder()
        self.pipeline=RealtimeSignalPipeline(MarketAnalyzer(),ProbabilityEngine(),SignalEngine(),TelegramFormatter(),SignalGuard())
        self.outcomes=SignalOutcomeRepository(); self.states=MarketStateRepository()
        self.websocket=BybitWebSocket(
            [f"kline.{interval}.{symbol}",f"tickers.{symbol}",f"orderbook.50.{symbol}"],
            self._handle,config or BybitWebSocketConfig()
        )

    async def _handle(self,message):
        topic=message.get("topic","")
        try:
            if topic.startswith("kline."):
                event=BybitNormalizer.kline(message); p=event.payload
                if not p.get("confirm"): return
                if self._last_candle_start==event.event_time: return
                self._last_candle_start=event.event_time
                self.closes.append(float(p["close"])); self.highs.append(float(p["high"])); self.lows.append(float(p["low"]))
            elif topic.startswith("tickers."):
                event=BybitNormalizer.ticker(message)
            elif topic.startswith("orderbook."):
                quality=self.orderbook.apply(message)
                if quality is not None:
                    if quality.code.value in {"orderbook_gap","impossible_value","malformed","stale"}:
                        await self._recover_orderbook()
                    return
                self._last_orderbook_update=datetime.now(timezone.utc)
                event=BybitNormalizer.orderbook(message)
                if self.publisher: await self.publisher(event)
                return
            else:
                return

            if self.publisher: await self.publisher(event)
            if topic.startswith("kline.") and len(self.closes)>=6:
                now=datetime.now(timezone.utc)
                snap=self.features.build(
                    self.symbol,event.event_time,list(self.closes),
                    highs=list(self.highs),lows=list(self.lows),orderbook=self.orderbook.state
                )
                state=self.builder.build(self.symbol,event.event_time,now,event.point_in_time_available_at,snap,{})
                def save_state():
                    with SessionLocal() as session:
                        self.states.save(session,state); session.commit()
                await asyncio.to_thread(save_state)
                signal,msg=self.pipeline.evaluate(state,float(event.payload["close"]),self._atr_from_features(snap))
                if signal.levels is not None and signal.direction.value!="none":
                    await self._record_pending(signal)
                if msg and self.telegram: await self.telegram.send(msg.text)
        except (KeyError,ValueError,TypeError):
            return

    async def _recover_orderbook(self):
        async with self._recovery_lock:
            try:
                payload=await self.rest.get_orderbook(symbol=self.symbol,limit=50)
                data=payload.get("result",{})
                self.orderbook.restore_snapshot(
                    data.get("b",[]),data.get("a",[]),data.get("u",0),
                    data.get("seq"),payload.get("time",0)
                )
                self._last_orderbook_update=datetime.now(timezone.utc)
            except (OrderBookError,KeyError,TypeError,ValueError,RuntimeError):
                return

    async def _orderbook_watchdog(self):
        while True:
            await asyncio.sleep(1)
            if await self._is_stopped():
                return
            quality=self.orderbook.mark_stale(int(datetime.now(timezone.utc).timestamp()*1000),self.ORDERBOOK_STALE_MS)
            if quality is not None:
                await self._recover_orderbook()

    async def _is_stopped(self):
        return getattr(self.websocket,"_stop").is_set()

    async def _record_pending(self,signal):
        levels=signal.levels
        if levels is None: return
        outcome=SignalOutcome(
            signal.signal_id,signal.symbol,signal.direction.value,signal.timestamp,
            (levels.entry_min+levels.entry_max)/2,levels.stop_loss,levels.tp1,levels.tp2,levels.tp3,
            signal.probability,OutcomeStatus.PENDING,horizon_minutes=60
        )
        def write():
            with SessionLocal() as session:
                self.outcomes.record_pending(session,outcome); session.commit()
        await asyncio.to_thread(write)

    def _atr_from_features(self,snapshot):
        for feature in snapshot.features:
            if feature.name=="atr_14" and feature.available:
                return feature.value
        return None

    async def bootstrap_orderbook(self):
        await self._recover_orderbook()

    async def run(self):
        await self.bootstrap_orderbook()
        watchdog=asyncio.create_task(self._orderbook_watchdog())
        try:
            await self.websocket.run()
        finally:
            watchdog.cancel()
            await asyncio.gather(watchdog,return_exceptions=True)

    async def stop(self):
        await self.websocket.stop()
