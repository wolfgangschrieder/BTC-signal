from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Any

@dataclass(frozen=True)
class MarketStateVector:
    symbol: str
    timestamp: datetime
    decision_time: datetime
    point_in_time_available_at: datetime
    vector_version: str
    feature_version: str
    numeric: dict[str, float | None]
    categorical: dict[str, str | None]
    availability: dict[str, bool]
    data_quality: dict[str, str]
    fingerprint: str

    @property
    def values(self):
        """Backward-compatible numeric view; canonical state lives in numeric/categorical."""
        return {**self.numeric, **self.categorical}

    @classmethod
    def build(
        cls, symbol, timestamp, decision_time, pit, values, availability,
        data_quality, feature_version="features-v1", vector_version="msv-v2",
        categorical=None,
    ):
        numeric={}
        categories=dict(categorical or {})
        for key,value in values.items():
            if isinstance(value,bool):
                numeric[key]=float(value)
            elif isinstance(value,(int,float)) or value is None:
                numeric[key]=value
            elif isinstance(value,str):
                categories[key]=value
            else:
                raise TypeError(f"unsupported MSV value type for {key}: {type(value).__name__}")
        canonical={
            "symbol":symbol,"timestamp":timestamp.isoformat(),
            "decision_time":decision_time.isoformat(),"pit":pit.isoformat(),
            "vector_version":vector_version,"feature_version":feature_version,
            "numeric":numeric,"categorical":categories,
            "availability":availability,"data_quality":data_quality,
        }
        fingerprint=sha256(json.dumps(canonical,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
        return cls(symbol,timestamp,decision_time,pit,vector_version,feature_version,
                   dict(numeric),categories,dict(availability),dict(data_quality),fingerprint)
