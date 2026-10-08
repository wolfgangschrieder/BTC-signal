from datetime import UTC, datetime

from research_os.data.models import EventType, RawEvent
from research_os.exchanges.bybit.schemas import BybitKline, BybitTicker, BybitTrade


class BybitNormalizer:
    @staticmethod
    def trades(raw, ingestion_time=None):
        """Validate the complete batch before exposing any partially applied state."""
        data = raw["data"]
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list) or not data:
            raise ValueError("Bybit trade data must be a nonempty batch")
        models = [BybitTrade.model_validate(item) for item in data]
        ingested = ingestion_time or datetime.now(UTC)
        return [
            RawEvent(
                source="bybit", event_type=EventType.TRADE, symbol=model.symbol,
                event_time=model.event_time(), ingestion_time=ingested,
                point_in_time_available_at=ingested, payload=model.model_dump(mode="json"),
            )
            for model in models
        ]

    @staticmethod
    def trade(raw, ingestion_time=None):
        events = BybitNormalizer.trades(raw, ingestion_time)
        if len(events) != 1:
            raise ValueError("Use trades() to normalize a multi-trade batch")
        return events[0]

    @staticmethod
    def ticker(raw,ingestion_time=None):
        data=raw["data"]; data=data[0] if isinstance(data,list) else data
        item={"symbol":data["symbol"],"last_price":data["lastPrice"],"bid_price":data.get("bid1Price"),"ask_price":data.get("ask1Price"),"funding_rate":data.get("fundingRate"),"open_interest":data.get("openInterest"),"next_funding_time_ms":int(data["nextFundingTime"]) if data.get("nextFundingTime") else None,"timestamp_ms":int(raw["ts"])}
        model=BybitTicker.model_validate(item); ingested=ingestion_time or datetime.now(UTC)
        return RawEvent(source="bybit",event_type=EventType.TICKER,symbol=model.symbol,event_time=datetime.fromtimestamp(model.timestamp_ms/1000,tz=UTC),ingestion_time=ingested,point_in_time_available_at=ingested,payload=model.model_dump(mode="json"))
    def kline(raw,ingestion_time=None):
        data=raw["data"]; item=data[0] if isinstance(data,list) else data
        item={**item,"symbol":raw["topic"].rsplit(".",1)[-1],"interval":str(item["interval"]),"start_ms":int(item["start"]),"timestamp_ms":int(raw["ts"])}
        model=BybitKline.model_validate(item); ingested=ingestion_time or datetime.now(UTC)
        return RawEvent(source="bybit",event_type=EventType.CANDLE,symbol=model.symbol,event_time=model.event_time(),ingestion_time=ingested,point_in_time_available_at=ingested,payload=model.model_dump(mode="json"))
    @staticmethod
    def orderbook(raw,ingestion_time=None):
        data=raw["data"]
        if not isinstance(data,dict): raise ValueError("Bybit orderbook data must be an object")
        ingested=ingestion_time or datetime.now(UTC); ts=int(raw["ts"])
        payload={"symbol":str(data["s"]),"update_id":int(data["u"]),"sequence":int(data["seq"]) if data.get("seq") is not None else None,"timestamp_ms":ts,"bids":data.get("b",[]),"asks":data.get("a",[]),"message_type":raw.get("type"),"topic":raw.get("topic")}
        et=EventType.ORDERBOOK_SNAPSHOT if raw.get("type")=="snapshot" else EventType.ORDERBOOK_UPDATE
        return RawEvent(source="bybit",event_type=et,symbol=payload["symbol"],event_time=datetime.fromtimestamp(ts/1000,tz=UTC),ingestion_time=ingested,point_in_time_available_at=ingested,payload=payload)
    @staticmethod
    def funding_history(raw, ingestion_time=None):
        ingested=ingestion_time or datetime.now(UTC)
        events=[]
        for item in raw.get("result",{}).get("list",[]):
            ts=int(item["fundingRateTimestamp"])
            events.append(RawEvent(source="bybit",event_type=EventType.FUNDING,symbol=str(item["symbol"]),event_time=datetime.fromtimestamp(ts/1000,tz=UTC),ingestion_time=ingested,point_in_time_available_at=ingested,payload={"symbol":str(item["symbol"]),"funding_rate":str(item["fundingRate"]),"timestamp_ms":ts}))
        return events

    @staticmethod
    def open_interest_history(raw, symbol="BTCUSDT", ingestion_time=None):
        ingested=ingestion_time or datetime.now(UTC)
        events=[]
        for item in raw.get("result",{}).get("list",[]):
            ts=int(item["timestamp"])
            events.append(RawEvent(source="bybit",event_type=EventType.OPEN_INTEREST,symbol=symbol,event_time=datetime.fromtimestamp(ts/1000,tz=UTC),ingestion_time=ingested,point_in_time_available_at=ingested,payload={"symbol":symbol,"open_interest":str(item["openInterest"]),"timestamp_ms":ts}))
        return events

    @staticmethod
    def liquidations(raw, ingestion_time=None):
        data=raw["data"]
        items=data if isinstance(data,list) else [data]
        ingested=ingestion_time or datetime.now(UTC)
        events=[]
        for item in items:
            ts=int(item.get("T",raw["ts"]))
            symbol=str(item["s"])
            events.append(RawEvent(source="bybit",event_type=EventType.LIQUIDATION,symbol=symbol,event_time=datetime.fromtimestamp(ts/1000,tz=UTC),ingestion_time=ingested,point_in_time_available_at=ingested,payload={"symbol":symbol,"side":str(item["S"]),"size":str(item["v"]),"price":str(item["p"]),"timestamp_ms":ts}))
        return events

    @staticmethod
    def liquidation(raw,ingestion_time=None):
        data=raw["data"]
        items=data if isinstance(data,list) else [data]
        item=items[0]
        ingested=ingestion_time or datetime.now(UTC)
        symbol=str(item["s"]); side=str(item["S"]); size=str(item["v"]); price=str(item["p"]); ts=int(item.get("T",raw["ts"]))
        return RawEvent(source="bybit",event_type=EventType.LIQUIDATION,symbol=symbol,event_time=datetime.fromtimestamp(ts/1000,tz=UTC),ingestion_time=ingested,point_in_time_available_at=ingested,payload={"symbol":symbol,"side":side,"size":size,"price":price,"timestamp_ms":ts})
