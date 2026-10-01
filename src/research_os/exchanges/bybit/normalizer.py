from datetime import datetime, timezone
from typing import Any
from research_os.data.models import EventType, RawEvent
from research_os.exchanges.bybit.schemas import BybitTicker, BybitTrade, BybitKline

class BybitNormalizer:
    @staticmethod
    def trade(raw,ingestion_time=None):
        data=raw["data"]; item=data[0] if isinstance(data,list) else data; model=BybitTrade.model_validate(item); ingested=ingestion_time or datetime.now(timezone.utc)
        return RawEvent(source="bybit",event_type=EventType.TRADE,symbol=model.symbol,event_time=model.event_time(),ingestion_time=ingested,point_in_time_available_at=ingested,payload=model.model_dump(mode="json"))
    @staticmethod
    def ticker(raw,ingestion_time=None):
        model=BybitTicker.model_validate(raw["data"]); ingested=ingestion_time or datetime.now(timezone.utc)
        return RawEvent(source="bybit",event_type=EventType.TICKER,symbol=model.symbol,event_time=datetime.fromtimestamp(model.timestamp_ms/1000,tz=timezone.utc),ingestion_time=ingested,point_in_time_available_at=ingested,payload=model.model_dump(mode="json"))
    @staticmethod
    def kline(raw,ingestion_time=None):
        data=raw["data"]; item=data[0] if isinstance(data,list) else data
        item={**item,"symbol":raw["topic"].rsplit(".",1)[-1],"interval":str(item["interval"]),"start_ms":int(item["start"]),"timestamp_ms":int(raw["ts"])}
        model=BybitKline.model_validate(item); ingested=ingestion_time or datetime.now(timezone.utc)
        return RawEvent(source="bybit",event_type=EventType.CANDLE,symbol=model.symbol,event_time=model.event_time(),ingestion_time=ingested,point_in_time_available_at=ingested,payload=model.model_dump(mode="json"))
    @staticmethod
    def orderbook(raw,ingestion_time=None):
        data=raw["data"]
        if not isinstance(data,dict): raise ValueError("Bybit orderbook data must be an object")
        ingested=ingestion_time or datetime.now(timezone.utc); ts=int(raw["ts"])
        payload={"symbol":str(data["s"]),"update_id":int(data["u"]),"sequence":int(data["seq"]) if data.get("seq") is not None else None,"timestamp_ms":ts,"bids":data.get("b",[]),"asks":data.get("a",[]),"message_type":raw.get("type"),"topic":raw.get("topic")}
        et=EventType.ORDERBOOK_SNAPSHOT if raw.get("type")=="snapshot" else EventType.ORDERBOOK_UPDATE
        return RawEvent(source="bybit",event_type=et,symbol=payload["symbol"],event_time=datetime.fromtimestamp(ts/1000,tz=timezone.utc),ingestion_time=ingested,point_in_time_available_at=ingested,payload=payload)
    @staticmethod
    def liquidation(raw,ingestion_time=None):
        data=raw["data"]
        items=data if isinstance(data,list) else [data]
        item=items[0]
        ingested=ingestion_time or datetime.now(timezone.utc)
        symbol=str(item["s"]); side=str(item["S"]); size=str(item["v"]); price=str(item["p"]); ts=int(item.get("T",raw["ts"]))
        return RawEvent(source="bybit",event_type=EventType.LIQUIDATION,symbol=symbol,event_time=datetime.fromtimestamp(ts/1000,tz=timezone.utc),ingestion_time=ingested,point_in_time_available_at=ingested,payload={"symbol":symbol,"side":side,"size":size,"price":price,"timestamp_ms":ts})
