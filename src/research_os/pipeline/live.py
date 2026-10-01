from __future__ import annotations
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from research_os.exchanges.bybit.normalizer import BybitNormalizer
from research_os.exchanges.bybit.ws import BybitWebSocket, BybitWebSocketConfig
from research_os.market.state_builder import MarketStateBuilder
from research_os.features.engine import FeatureEngine
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.probability import ProbabilityEngine
from research_os.notifications.telegram import TelegramFormatter
from research_os.notifications.telegram_client import TelegramClient
from research_os.signals.engine import SignalEngine
from research_os.signals.guard import SignalGuard
from research_os.pipeline.realtime import RealtimeSignalPipeline

EventPublisher=Callable[[object],Awaitable[None]]

class LiveSignalService:
    """Read-only Bybit live loop. It never sends trading requests."""
    def __init__(self,symbol="BTCUSDT",interval="1",publisher: EventPublisher|None=None,telegram: TelegramClient|None=None,config=None):
        self.symbol=symbol; self.interval=interval; self.publisher=publisher; self.telegram=telegram
        self.closes=deque(maxlen=200); self._last_candle_start=None
        self.features=FeatureEngine(); self.builder=MarketStateBuilder()
        self.pipeline=RealtimeSignalPipeline(MarketAnalyzer(),ProbabilityEngine(),SignalEngine(),TelegramFormatter(),SignalGuard())
        topics=[f"kline.{interval}.{symbol}",f"tickers.{symbol}",f"orderbook.50.{symbol}"]
        self.websocket=BybitWebSocket(topics,self._handle,config or BybitWebSocketConfig())
    async def _handle(self,message):
        topic=message.get("topic","")
        try:
            if topic.startswith("kline."):
                event=BybitNormalizer.kline(message); p=event.payload
                if not p.get("confirm"): return
                if self._last_candle_start == event.event_time: return
                self._last_candle_start=event.event_time
                self.closes.append(float(p["close"]))
            elif topic.startswith("tickers."): event=BybitNormalizer.ticker(message)
            elif topic.startswith("orderbook."): return
            else: return
            if self.publisher: await self.publisher(event)
            if topic.startswith("kline.") and len(self.closes)>=6:
                now=datetime.now(timezone.utc)
                snap=self.features.build(self.symbol,event.event_time,list(self.closes))
                state=self.builder.build(self.symbol,event.event_time,now,event.point_in_time_available_at,snap,{})
                price=float(event.payload["close"])
                atr=self._range_proxy()
                signal,msg=self.pipeline.evaluate(state,price,atr)
                if msg and self.telegram: await self.telegram.send(msg.text)
        except (KeyError,ValueError,TypeError):
            return
    def _range_proxy(self):
        if len(self.closes)<2: return None
        moves=[abs(self.closes[i]-self.closes[i-1]) for i in range(max(1,len(self.closes)-15),len(self.closes))]
        return sum(moves)/len(moves) if moves else None
    async def run(self): await self.websocket.run()
    async def stop(self): await self.websocket.stop()
