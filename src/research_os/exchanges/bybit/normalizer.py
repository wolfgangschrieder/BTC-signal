from datetime import datetime, timezone
from typing import Any
from research_os.data.models import EventType, RawEvent
from research_os.exchanges.bybit.schemas import BybitTicker, BybitTrade

class BybitNormalizer:
    @staticmethod
    def trade(raw: dict[str, Any], ingestion_time: datetime | None = None) -> RawEvent:
        data = raw["data"]
        item = data[0] if isinstance(data, list) else data
        model = BybitTrade.model_validate(item)
        ingested = ingestion_time or datetime.now(timezone.utc)
        event_time = model.event_time()
        return RawEvent(
            source="bybit",
            event_type=EventType.TRADE,
            symbol=model.symbol,
            event_time=event_time,
            ingestion_time=ingested,
            point_in_time_available_at=ingested,
            payload=model.model_dump(mode="json"),
        )

    @staticmethod
    def ticker(raw: dict[str, Any], ingestion_time: datetime | None = None) -> RawEvent:
        data = raw["data"]
        model = BybitTicker.model_validate(data)
        ingested = ingestion_time or datetime.now(timezone.utc)
        return RawEvent(
            source="bybit",
            event_type=EventType.TICKER,
            symbol=model.symbol,
            event_time=datetime.fromtimestamp(model.timestamp_ms / 1000, tz=timezone.utc),
            ingestion_time=ingested,
            point_in_time_available_at=ingested,
            payload=model.model_dump(mode="json"),
        )


    @staticmethod
    def orderbook(raw: dict[str, Any], ingestion_time: datetime | None = None) -> RawEvent:
        data = raw["data"]
        if not isinstance(data, dict):
            raise ValueError("Bybit orderbook data must be an object")
        ingested = ingestion_time or datetime.now(timezone.utc)
        ts = int(raw["ts"])
        payload = {
            "symbol": str(data["s"]),
            "update_id": int(data["u"]),
            "sequence": int(data["seq"]) if data.get("seq") is not None else None,
            "timestamp_ms": ts,
            "bids": data.get("b", []),
            "asks": data.get("a", []),
            "message_type": raw.get("type"),
            "topic": raw.get("topic"),
        }
        event_type = EventType.ORDERBOOK_SNAPSHOT if raw.get("type") == "snapshot" else EventType.ORDERBOOK_UPDATE
        return RawEvent(source="bybit", event_type=event_type, symbol=payload["symbol"],
                        event_time=datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
                        ingestion_time=ingested, point_in_time_available_at=ingested,
                        payload=payload)
