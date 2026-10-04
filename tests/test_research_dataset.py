from datetime import datetime, timedelta, timezone

import pytest

from research_os.research.dataset import build_dataset_row


def _inputs():
    decision=datetime(2026,1,1,tzinfo=timezone.utc)
    return decision,{
        "state_id":"state-1",
        "timestamp":decision,
        "point_in_time_available_at":decision,
        "vector":{
            "values":{"close":100.0,"orderflow_ofi_zscore":1.2},
            "availability":{"close":True,"orderflow_ofi_zscore":True},
        },
    },{
        "symbol":"BTCUSDT","direction":"long","signal_time":decision,
        "entry_price":100.0,"probability":0.75,"horizon_minutes":60,
        "resolved_at":decision+timedelta(hours=1),
        "realized_return":0.01,"mfe":0.02,"mae":-0.005,
    }


def test_dataset_row_contains_signal_metadata_and_provenance():
    decision,state,outcome=_inputs()
    row=build_dataset_row(
        dataset_version="test-v1",
        state=state,
        outcome=outcome,
        cross_market={"values":{"SPX":5000.0},"sources":{"SPX":"fred"},"available":True},
        external={
            "event_count":2,"high_impact_count":1,"weighted_sentiment":0.4,
            "max_relevance":0.9,"categories":("macro",),"event_ids":("evt-2","evt-1"),
        },
    )
    assert row.features["signal_direction"]=="long"
    assert row.features["signal_probability"]==0.75
    assert row.external_event_ids==("evt-1","evt-2")
    assert any(item["type"]=="market_state" for item in row.provenance)
    assert any(item["type"]=="external_event" and item["event_id"]=="evt-1" for item in row.provenance)


def test_dataset_row_rejects_future_state_availability():
    decision,state,outcome=_inputs()
    state["point_in_time_available_at"]=decision+timedelta(seconds=1)
    with pytest.raises(ValueError,match="PIT"):
        build_dataset_row(dataset_version="test-v1",state=state,outcome=outcome)


def test_dataset_row_rejects_misaligned_state_time():
    decision,state,outcome=_inputs()
    state["timestamp"]=decision-timedelta(minutes=1)
    with pytest.raises(ValueError,match="timestamp"):
        build_dataset_row(dataset_version="test-v1",state=state,outcome=outcome)
