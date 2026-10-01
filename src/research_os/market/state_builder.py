from __future__ import annotations
from datetime import datetime
from .state_vector import MarketStateVector
from research_os.features.models import FeatureSnapshot

def _split(values):
    numeric={}; categorical={}
    for key,value in values.items():
        if isinstance(value,bool):
            numeric[key]=float(value)
        elif isinstance(value,(int,float)) or value is None:
            numeric[key]=value
        elif isinstance(value,str):
            categorical[key]=value
        else:
            raise TypeError(f"unsupported MSV value type for {key}: {type(value).__name__}")
    return numeric,categorical

class MarketStateBuilder:
    def build(self,symbol,timestamp,decision_time,pit,snapshot,data_quality=None,extra_values=None,extra_availability=None):
        values={f.name:f.value for f in snapshot.features}
        availability={f.name:f.available for f in snapshot.features}
        mtf_state=getattr(snapshot,"state",None)
        if mtf_state is not None:
            values.update({
                "mtf_trend":mtf_state.trend,"mtf_momentum":mtf_state.momentum,
                "mtf_volatility":mtf_state.volatility,"mtf_structure":mtf_state.structure,
                "mtf_breakout":mtf_state.breakout,"mtf_pullback":mtf_state.pullback,
                "mtf_alignment":mtf_state.alignment,"mtf_conflict":float(mtf_state.conflict),
                "mtf_strength":mtf_state.strength})
            for k in ("mtf_trend","mtf_momentum","mtf_volatility","mtf_structure","mtf_breakout","mtf_pullback","mtf_alignment","mtf_conflict","mtf_strength"):
                availability[k]=True
        if extra_values: values.update(extra_values)
        if extra_availability: availability.update(extra_availability)
        numeric,categorical=_split(values)
        return MarketStateVector.build(symbol,timestamp,decision_time,pit,numeric,availability,data_quality or {},snapshot.version,categorical=categorical)

    def build_multi(self,symbol,timestamp,decision_time,pit,snapshot,base_snapshot=None,data_quality=None,extra_values=None,extra_availability=None):
        values={}; availability={}
        if base_snapshot is not None:
            for f in base_snapshot.features:
                values[f.name]=f.value; availability[f.name]=f.available
        for timeframe,fs in snapshot.snapshots.items():
            prefix=timeframe.value
            for f in fs.features:
                values[f"tf_{prefix}_{f.name}"]=f.value
                availability[f"tf_{prefix}_{f.name}"]=f.available
        if snapshot.state is not None:
            s=snapshot.state
            values.update({"mtf_trend":s.trend,"mtf_momentum":s.momentum,"mtf_volatility":s.volatility,"mtf_structure":s.structure,"mtf_breakout":s.breakout,"mtf_pullback":s.pullback,"mtf_alignment":s.alignment,"mtf_conflict":float(s.conflict),"mtf_strength":s.strength})
            for k in ("mtf_trend","mtf_momentum","mtf_volatility","mtf_structure","mtf_breakout","mtf_pullback","mtf_alignment","mtf_conflict","mtf_strength"):
                availability[k]=True
        if extra_values: values.update(extra_values)
        if extra_availability: availability.update(extra_availability)
        numeric,categorical=_split(values)
        return MarketStateVector.build(symbol,timestamp,decision_time,pit,numeric,availability,data_quality or {},snapshot.version,categorical=categorical)
