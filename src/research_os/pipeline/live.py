from __future__ import annotations
from collections import deque
from research_os.features.timeframes import OHLCVBar, MultiTimeframeFeatureEngine
from collections.abc import Awaitable,Callable
from datetime import datetime,timezone
import asyncio
from research_os.exchanges.bybit.normalizer import BybitNormalizer
from research_os.exchanges.bybit.orderbook import OrderBook, OrderBookError
from research_os.exchanges.bybit.client import BybitRestClient
from research_os.exchanges.bybit.ws import BybitWebSocket,BybitWebSocketConfig
from research_os.market.state_builder import MarketStateBuilder
from research_os.features.engine import FeatureEngine
from research_os.features.orderflow import OrderFlowEngine, TradeObservation, snapshot_features
from research_os.features.derivatives import DerivativesEngine, snapshot_features as derivatives_features
from research_os.features.liquidity import LiquidityEngine, snapshot_features as liquidity_features
from research_os.signals.guard import SignalExecutionContext
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

    def __init__(self,symbol="BTCUSDT",interval="1",publisher:EventPublisher|None=None,telegram:TelegramClient|None=None,config=None,guard:SignalGuard|None=None):
        self.symbol=symbol; self.interval=interval; self.publisher=publisher
        self.telegram=telegram
        self.closes=deque(maxlen=2000); self.highs=deque(maxlen=2000); self.lows=deque(maxlen=2000); self.bars_1m=deque(maxlen=2000); self.trades=deque(maxlen=5000)
        self.orderflow=OrderFlowEngine(); self.cumulative_delta=0.0; self.previous_flow_price=None; self.previous_flow_cvd=0.0
        self.derivatives=DerivativesEngine(); self.derivatives_funding=None; self.derivatives_oi=None; self.previous_derivatives_price=None; self.previous_funding=None; self.previous_oi=None; self.liquidations=deque(maxlen=5000)
        self.mtf=MultiTimeframeFeatureEngine()
        self.liquidity=LiquidityEngine()
        self._liquidity_state=None
        self._last_candle_start=None
        self.orderbook=OrderBook(symbol,max_levels=50)
        self.rest=BybitRestClient()
        self._last_orderbook_update=datetime.min.replace(tzinfo=timezone.utc)
        self._recovery_lock=asyncio.Lock()
        self.features=FeatureEngine(); self.builder=MarketStateBuilder()
        self.pipeline=RealtimeSignalPipeline(MarketAnalyzer(),ProbabilityEngine(),SignalEngine(),TelegramFormatter(),guard or SignalGuard())
        self.outcomes=SignalOutcomeRepository(); self.states=MarketStateRepository()
        self.websocket=BybitWebSocket(
            [f"kline.{interval}.{symbol}",f"tickers.{symbol}",f"orderbook.50.{symbol}",f"publicTrade.{symbol}",f"allLiquidation.{symbol}"],
            self._handle,config or BybitWebSocketConfig()
        )

    async def _handle(self,message):
        topic=message.get("topic","")
        try:
            if topic.startswith("publicTrade."):
                event=BybitNormalizer.trade(message); p=event.payload
                self.trades.append(TradeObservation(event.event_time,float(p["price"]),float(p["size"]),str(p["side"])))
                flow=self.orderflow.build([self.trades[-1]],event.event_time,cumulative_delta_base=self.cumulative_delta,previous_price=self.previous_flow_price,previous_cumulative_delta=self.previous_flow_cvd)
                if flow.available:
                    self.cumulative_delta=flow.cumulative_delta or self.cumulative_delta
                    self.previous_flow_price=float(p["price"])
                    self.previous_flow_cvd=self.cumulative_delta
                if self.publisher: await self.publisher(event)
                return
            if topic.startswith("allLiquidation."):
                events=BybitNormalizer.liquidations(message)
                for event in events:
                    p=event.payload
                    self.liquidations.append((event.event_time,str(p["side"]),float(p["size"])))
                    if self.publisher: await self.publisher(event)
                return
            if topic.startswith("kline."):
                event=BybitNormalizer.kline(message); p=event.payload
                if not p.get("confirm"): return
                if self._last_candle_start==event.event_time: return
                self._last_candle_start=event.event_time
                self.closes.append(float(p["close"])); self.highs.append(float(p["high"])); self.lows.append(float(p["low"]))
                self.bars_1m.append(OHLCVBar(event.event_time,float(p["open"]),float(p["high"]),float(p["low"]),float(p["close"]),float(p["volume"])))
            elif topic.startswith("tickers."):
                event=BybitNormalizer.ticker(message)
                self.derivatives_funding=float(event.payload["funding_rate"]) if event.payload.get("funding_rate") is not None else self.derivatives_funding
                self.derivatives_oi=float(event.payload["open_interest"]) if event.payload.get("open_interest") is not None else self.derivatives_oi
            elif topic.startswith("orderbook."):
                quality=self.orderbook.apply(message)
                if quality is not None:
                    if quality.code.value in {"orderbook_gap","impossible_value","malformed","stale"}:
                        await self._recover_orderbook()
                    return
                self._last_orderbook_update=datetime.now(timezone.utc)
                book_state=self.orderbook.state
                if book_state.valid and book_state.bids and book_state.asks:
                    mid=(float(book_state.bids[0].price)+float(book_state.asks[0].price))/2
                    self._liquidity_state=self.liquidity.build(book_state,mid,book_state.last_event_time_ms)
                else:
                    self._liquidity_state=None
                event=BybitNormalizer.orderbook(message)
                event.payload["valid"]=self.orderbook.state.valid
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
                mtf_snapshot=self.mtf.build(self.symbol,list(self.bars_1m),event.event_time,as_of=now)
                flow=self.orderflow.build(list(self.trades),event.event_time,cumulative_delta_base=0.0,previous_price=self.previous_flow_price,previous_cumulative_delta=self.previous_flow_cvd)
                flow_values=snapshot_features(flow)
                flow_values["orderflow_cumulative_delta"]=self.cumulative_delta
                cutoff=event.event_time.timestamp()-3600
                long_liq=sum(size for ts,side,size in self.liquidations if ts.timestamp() >= cutoff and side.lower()=="buy")
                short_liq=sum(size for ts,side,size in self.liquidations if ts.timestamp() >= cutoff and side.lower()=="sell")
                deriv=self.derivatives.build(event.event_time,float(event.payload["close"]),self.derivatives_funding,self.derivatives_oi,self.previous_derivatives_price,self.previous_funding,self.previous_oi,long_liq,short_liq)
                deriv_values=derivatives_features(deriv)
                if deriv.state is not None:
                    extra_state=deriv.state
                    extra={
                        **flow_values,
                        **deriv_values,
                        "derivatives_state_strength": extra_state.strength,
                        "derivatives_state_conflict": 1.0 if extra_state.alignment == "conflicting" else 0.0,
                        "derivatives_funding_positive": 1.0 if extra_state.funding_regime == "positive_funding" else 0.0,
                        "derivatives_funding_negative": 1.0 if extra_state.funding_regime == "negative_funding" else 0.0,
                        "derivatives_oi_rising": 1.0 if extra_state.oi_regime == "rising" else 0.0,
                        "derivatives_oi_falling": 1.0 if extra_state.oi_regime == "falling" else 0.0,
                        "derivatives_liquidation_stress": 1.0 if extra_state.liquidation_stress == "observed" else 0.0,
                    }
                else:
                    extra={**flow_values,**deriv_values}
                extra["orderflow_cumulative_delta"]=self.cumulative_delta
                price=float(event.payload["close"])
                liquidity_state=self._liquidity_state
                if liquidity_state is None or liquidity_state.timestamp_ms != self.orderbook.state.last_event_time_ms:
                    liquidity_state=self.liquidity.build(self.orderbook.state,price,self.orderbook.state.last_event_time_ms)
                    self._liquidity_state=liquidity_state
                liquidity_values=liquidity_features(liquidity_state)
                extra.update(liquidity_values)
                availability={key: ((flow.available and value is not None) if key.startswith("orderflow_") else (deriv.available and value is not None)) for key,value in extra.items()}
                for key,value in liquidity_values.items(): availability[key]=liquidity_state.valid and value is not None
                state=self.builder.build_multi(self.symbol,event.event_time,now,event.point_in_time_available_at,mtf_snapshot,base_snapshot=snap,extra_values=extra,extra_availability=availability)
                self.previous_derivatives_price=float(event.payload["close"])
                self.previous_funding=self.derivatives_funding
                self.previous_oi=self.derivatives_oi
                def save_state():
                    with SessionLocal() as session:
                        self.states.save(session,state); session.commit()
                await asyncio.to_thread(save_state)
                spread_bps=None
                book_state=self.orderbook.state
                if book_state.valid and book_state.bids and book_state.asks:
                    bid=float(book_state.bids[0].price); ask=float(book_state.asks[0].price)
                    mid=(bid+ask)/2
                    if mid>0: spread_bps=(ask-bid)/mid*10000
                age_ms=None
                if book_state.last_event_time_ms>0:
                    age_ms=max(0,int(datetime.now(timezone.utc).timestamp()*1000)-book_state.last_event_time_ms)
                context=SignalExecutionContext(latency_ms=self.websocket.latency_ms,spread_bps=spread_bps,orderbook_valid=book_state.valid,orderbook_age_ms=age_ms)
                clusters=tuple(liquidity_state.bid_clusters+liquidity_state.ask_clusters) if liquidity_state.valid else ()
                signal,msg=self.pipeline.evaluate(state,price,self._atr_from_features(snap),context=context,liquidity_clusters=clusters)
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

    async def bootstrap_derivatives_history(self):
        if not self.publisher:
            return
        try:
            funding=await self.rest.get_funding_history(symbol=self.symbol,limit=200)
            await self.publisher_many(BybitNormalizer.funding_history(funding))
            oi=await self.rest.get_open_interest(symbol=self.symbol,interval_time="5min",limit=200)
            await self.publisher_many(BybitNormalizer.open_interest_history(oi,self.symbol))
        except (KeyError,TypeError,ValueError,RuntimeError):
            return

    async def publisher_many(self, events):
        for event in events:
            await self.publisher(event)

    async def bootstrap_orderbook(self):
        await self._recover_orderbook()

    async def run(self):
        await self.bootstrap_derivatives_history()
        await self.bootstrap_orderbook()
        watchdog=asyncio.create_task(self._orderbook_watchdog())
        try:
            await self.websocket.run()
        finally:
            watchdog.cancel()
            await asyncio.gather(watchdog,return_exceptions=True)

    async def stop(self):
        await self.websocket.stop()
