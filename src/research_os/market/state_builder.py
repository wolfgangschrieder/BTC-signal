from __future__ import annotations
from datetime import datetime
from .state_vector import MarketStateVector
from research_os.features.models import FeatureSnapshot

class MarketStateBuilder:
    """Builds a reproducible MSV from features and explicit availability metadata."""
    def build(self, symbol: str, timestamp: datetime, decision_time: datetime, pit: datetime, snapshot: FeatureSnapshot, data_quality: dict[str,str] | None = None) -> MarketStateVector:
        values={f.name:f.value for f in snapshot.features}
        availability={f.name:f.available for f in snapshot.features}
        if snapshot.state is not None:
            state=snapshot.state
            values.update({
                "mtf_trend": state.trend,
                "mtf_momentum": state.momentum,
                "mtf_volatility": state.volatility,
                "mtf_structure": state.structure,
                "mtf_breakout": state.breakout,
                "mtf_pullback": state.pullback,
                "mtf_alignment": state.alignment,
                "mtf_conflict": float(state.conflict),
                "mtf_strength": state.strength,
            })
            for key in ("mtf_trend","mtf_momentum","mtf_volatility","mtf_structure","mtf_breakout","mtf_pullback","mtf_alignment","mtf_conflict","mtf_strength"):
                availability[key]=True
        quality=data_quality or {}
        return MarketStateVector.build(symbol,timestamp,decision_time,pit,values,availability,quality,snapshot.version)


    def build_multi(self, symbol: str, timestamp: datetime, decision_time: datetime, pit: datetime, snapshot, base_snapshot: FeatureSnapshot | None = None, data_quality: dict[str,str] | None = None) -> MarketStateVector:
        """Build one unified MSV with namespaced multi-timeframe features."""
        availability={}
        values={}
        if base_snapshot is not None:
            for feature in base_snapshot.features:
                values[feature.name]=feature.value
                availability[feature.name]=feature.available
        for timeframe, feature_snapshot in snapshot.snapshots.items():
            prefix=timeframe.value
            for feature in feature_snapshot.features:
                key=f"tf_{prefix}_{feature.name}"
                values[key]=feature.value
                availability[key]=feature.available
        quality=data_quality or {}
        return MarketStateVector.build(symbol,timestamp,decision_time,pit,values,availability,quality,snapshot.version)
