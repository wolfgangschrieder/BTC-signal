from __future__ import annotations
from datetime import datetime
from .state_vector import MarketStateVector
from research_os.features.models import FeatureSnapshot

class MarketStateBuilder:
    """Builds a reproducible MSV from features and explicit availability metadata."""
    def build(self, symbol: str, timestamp: datetime, decision_time: datetime, pit: datetime, snapshot: FeatureSnapshot, data_quality: dict[str,str] | None = None) -> MarketStateVector:
        values={f.name:f.value for f in snapshot.features}
        availability={f.name:f.available for f in snapshot.features}
        quality=data_quality or {}
        return MarketStateVector.build(symbol,timestamp,decision_time,pit,values,availability,quality,snapshot.version)


    def build_multi(self, symbol: str, timestamp: datetime, decision_time: datetime, pit: datetime, snapshot, data_quality: dict[str,str] | None = None) -> MarketStateVector:
        """Build one unified MSV with namespaced multi-timeframe features."""
        availability={}
        values={}
        for timeframe, feature_snapshot in snapshot.snapshots.items():
            prefix=timeframe.value
            for feature in feature_snapshot.features:
                key=f"tf_{prefix}_{feature.name}"
                values[key]=feature.value
                availability[key]=feature.available
        quality=data_quality or {}
        return MarketStateVector.build(symbol,timestamp,decision_time,pit,values,availability,quality,snapshot.version)
