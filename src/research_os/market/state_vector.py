from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Mapping

@dataclass(slots=True, frozen=True)
class StateVector:
    """Immutable hot-path market fingerprint. No Pydantic, DB, or serialization on construction."""
    symbol: str
    timestamp: datetime
    decision_time: datetime
    point_in_time_available_at: datetime
    version: str
    feature_version: str
    numeric: Mapping[str, float|int|None]
    categorical: Mapping[str, str|None]
    availability: Mapping[str, bool]
    fingerprint: str

    @property
    def values(self) -> Mapping[str, object]:
        return {**self.numeric, **self.categorical}

    @staticmethod
    def fingerprint_for(*, symbol: str, timestamp: datetime, decision_time: datetime,
                        point_in_time_available_at: datetime, version: str, feature_version: str,
                        numeric: Mapping[str, float|int|None],
                        categorical: Mapping[str, str|None],
                        availability: Mapping[str, bool]) -> str:
        payload={
            "symbol":symbol,
            "timestamp":timestamp.isoformat(),
            "decision_time":decision_time.isoformat(),
            "point_in_time_available_at":point_in_time_available_at.isoformat(),
            "version":version,
            "feature_version":feature_version,
            "numeric":dict(sorted(numeric.items())),
            "categorical":dict(sorted(categorical.items())),
            "availability":dict(sorted(availability.items())),
        }
        return hashlib.sha256(json.dumps(payload,separators=(",",":"),sort_keys=True,default=str).encode()).hexdigest()

    @classmethod
    def build(cls, *, symbol: str, timestamp: datetime, decision_time: datetime,
              point_in_time_available_at: datetime, version: str, feature_version: str,
              numeric: Mapping[str, float|int|None]=(), categorical: Mapping[str,str|None]=(),
              availability: Mapping[str,bool]=()) -> "StateVector":
        if not symbol: raise ValueError("symbol must not be empty")
        for name,dt in (("timestamp",timestamp),("decision_time",decision_time),("point_in_time_available_at",point_in_time_available_at)):
            if dt.tzinfo is None: raise ValueError(f"{name} must be timezone-aware")
        if point_in_time_available_at > decision_time:
            raise ValueError("point_in_time_available_at must not exceed decision_time")
        numeric=dict(numeric)
        categorical=dict(categorical)
        availability=dict(availability)
        for key,value in numeric.items():
            if isinstance(value,bool) or not isinstance(value,(int,float,type(None))):
                raise TypeError(f"numeric feature {key!r} must be int, float, or None")
        for key,value in categorical.items():
            if value is not None and not isinstance(value,str):
                raise TypeError(f"categorical feature {key!r} must be str or None")
        for key,value in availability.items():
            if not isinstance(value,bool): raise TypeError(f"availability {key!r} must be bool")
        fp=cls.fingerprint_for(symbol=symbol,timestamp=timestamp,decision_time=decision_time,
                               point_in_time_available_at=point_in_time_available_at,version=version,
                               feature_version=feature_version,numeric=numeric,
                               categorical=categorical,availability=availability)
        return cls(symbol,timestamp,decision_time,point_in_time_available_at,version,
                   feature_version,numeric,categorical,availability,fp)
