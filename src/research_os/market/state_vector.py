from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json

@dataclass(frozen=True)
class MarketStateVector:
    symbol: str
    timestamp: datetime
    decision_time: datetime
    point_in_time_available_at: datetime
    vector_version: str
    feature_version: str
    values: dict[str, float | None]
    availability: dict[str, bool]
    data_quality: dict[str, str]
    fingerprint: str

    @classmethod
    def build(cls, symbol, timestamp, decision_time, pit, values, availability, data_quality, feature_version="features-v1", vector_version="msv-v1"):
        canonical={"symbol":symbol,"timestamp":timestamp.isoformat(),"decision_time":decision_time.isoformat(),"pit":pit.isoformat(),"vector_version":vector_version,"feature_version":feature_version,"values":values,"availability":availability,"data_quality":data_quality}
        fingerprint=sha256(json.dumps(canonical,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
        return cls(symbol,timestamp,decision_time,pit,vector_version,feature_version,dict(values),dict(availability),dict(data_quality),fingerprint)
