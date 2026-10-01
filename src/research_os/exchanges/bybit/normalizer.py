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
