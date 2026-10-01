from __future__ import annotations
from decimal import Decimal
from sqlalchemy.orm import Session
from research_os.data.models import EventType, RawEvent
from research_os.market.models import Trade, Candle, OrderBookSnapshot, OrderBookUpdate, MarketSnapshot
from research_os.derivatives.models import FundingRate, OpenInterest, Liquidation

class NormalizedMarketDataStore:
    """Projects validated RawEvents into typed time-series tables in the same transaction."""
    def persist(self, session: Session, event: RawEvent, raw_event_id: int) -> None:
        p=event.payload
        common=dict(event_time=event.event_time,ingestion_time=event.ingestion_time,point_in_time_available_at=event.point_in_time_available_at,symbol=event.symbol or str(p.get("symbol")),source=event.source,raw_event_id=raw_event_id)
        if event.event_type is EventType.TRADE:
            session.add(Trade(**common,exchange_trade_id=p.get("trade_id") or p.get("execId"),price=Decimal(str(p["price"])),size=Decimal(str(p["size"])),side=str(p["side"])))
        elif event.event_type is EventType.CANDLE:
            session.merge(Candle(**common,interval=str(p["interval"]),open=Decimal(str(p["open"])),high=Decimal(str(p["high"])),low=Decimal(str(p["low"])),close=Decimal(str(p["close"])),volume=Decimal(str(p["volume"])),turnover=Decimal(str(p["turnover"])) if p.get("turnover") is not None else None))
        elif event.event_type in (EventType.ORDERBOOK_SNAPSHOT, EventType.ORDERBOOK_UPDATE):
            update_id=int(p["update_id"]); sequence=p.get("sequence")
            if event.event_type is EventType.ORDERBOOK_SNAPSHOT:
                bids=[{"price":str(x[0]),"size":str(x[1])} for x in p.get("bids",[])]; asks=[{"price":str(x[0]),"size":str(x[1])} for x in p.get("asks",[])]
                session.add(OrderBookSnapshot(**common,update_id=update_id,sequence=sequence,bids=bids,asks=asks,valid=bool(p.get("valid", True))))
            else:
                for side,key in (("buy","bids"),("sell","asks")):
                    for level in p.get(key,[]):
                        session.add(OrderBookUpdate(**common,update_id=update_id,sequence=sequence,side=side,price=Decimal(str(level[0])),size=Decimal(str(level[1])),action="delete" if Decimal(str(level[1]))==0 else "update"))
        elif event.event_type is EventType.TICKER:
            last=Decimal(str(p["last_price"])); bid=Decimal(str(p["bid_price"])) if p.get("bid_price") is not None else None; ask=Decimal(str(p["ask_price"])) if p.get("ask_price") is not None else None
            mid=(bid+ask)/2 if bid is not None and ask is not None else None; spread=ask-bid if bid is not None and ask is not None else None
            session.add(MarketSnapshot(**common,last_price=last,bid=bid,ask=ask,mid_price=mid,spread=spread,volume_24h=None,open_interest=Decimal(str(p["open_interest"])) if p.get("open_interest") is not None else None,funding_rate=Decimal(str(p["funding_rate"])) if p.get("funding_rate") is not None else None,orderbook_valid=None))
            if p.get("funding_rate") is not None:
                session.add(FundingRate(**common,funding_rate=Decimal(str(p["funding_rate"])),funding_time=event.event_time))
            if p.get("open_interest") is not None:
                session.add(OpenInterest(**common,open_interest=Decimal(str(p["open_interest"]))))
        elif event.event_type is EventType.LIQUIDATION:
            session.add(Liquidation(**common,side=str(p["side"]),price=Decimal(str(p["price"])),size=Decimal(str(p["size"]))))
