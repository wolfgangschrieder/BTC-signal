from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ResearchDatasetRow:
    dataset_version: str
    symbol: str
    decision_time: datetime
    entry_price: float
    horizon_minutes: int
    outcome_time: datetime
    return_pct: float
    mfe_pct: float
    mae_pct: float
    features: dict[str, Any]
    cross_market: dict[str, Any]
    external_event_count: int
    external_high_impact_count: int
    external_weighted_sentiment: float | None
    external_max_relevance: float
    external_categories: tuple[str, ...]
    external_event_ids: tuple[str, ...]
    provenance: tuple[dict[str, Any], ...]


def build_dataset_row(
    *,
    dataset_version: str,
    state: dict[str, Any],
    outcome: dict[str, Any],
    cross_market: dict[str, Any] | None = None,
    external: dict[str, Any] | None = None,
) -> ResearchDatasetRow:
    """Build one immutable, PIT-auditable training/evaluation row."""
    decision_time=outcome["signal_time"]
    state_time=state["timestamp"]
    state_pit=state["point_in_time_available_at"]
    if state_time != decision_time:
        raise ValueError("state timestamp must equal outcome signal_time")
    if state_pit > decision_time:
        raise ValueError("state violates PIT at decision time")

    required=("entry_price","horizon_minutes","resolved_at","realized_return","mfe","mae")
    if any(outcome.get(key) is None for key in required):
        raise ValueError("resolved outcome is incomplete")

    values=(state.get("vector") or {}).get("values", state.get("vector") or {})
    availability=(state.get("vector") or {}).get("availability", {})
    features=dict(values)
    features["signal_direction"]=str(outcome["direction"])
    features["signal_probability"]=float(outcome["probability"])
    features["_feature_availability"]=dict(availability)

    cm=dict(cross_market or {})
    ext=dict(external or {})
    event_ids=tuple(sorted(str(x) for x in ext.get("event_ids", ())))
    categories=tuple(sorted(str(x) for x in ext.get("categories", ())))

    provenance=[
        {"type":"market_state","state_id":str(state["state_id"]),
         "timestamp":state_time.isoformat(),"point_in_time_available_at":state_pit.isoformat()},
    ]
    for source in cm.get("sources", {}).values():
        provenance.append({"type":"cross_market","source":str(source)})
    for event_id in event_ids:
        provenance.append({"type":"external_event","event_id":event_id})

    return ResearchDatasetRow(
        dataset_version=dataset_version,
        symbol=str(outcome["symbol"]),
        decision_time=decision_time,
        entry_price=float(outcome["entry_price"]),
        horizon_minutes=int(outcome["horizon_minutes"]),
        outcome_time=outcome["resolved_at"],
        return_pct=float(outcome["realized_return"]),
        mfe_pct=float(outcome["mfe"]),
        mae_pct=float(outcome["mae"]),
        features=features,
        cross_market=cm,
        external_event_count=int(ext.get("event_count", 0)),
        external_high_impact_count=int(ext.get("high_impact_count", 0)),
        external_weighted_sentiment=(
            None if ext.get("weighted_sentiment") is None
            else float(ext["weighted_sentiment"])
        ),
        external_max_relevance=float(ext.get("max_relevance", 0.0)),
        external_categories=categories,
        external_event_ids=event_ids,
        provenance=tuple(provenance),
    )
