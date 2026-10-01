from datetime import datetime, timezone, timedelta
import pytest
from research_os.market.state_vector import StateVector
def test_state_vector_builds_and_fingerprints_categorical_state():
    ts=datetime(2026,1,1,tzinfo=timezone.utc)
    a=StateVector.build(symbol="BTCUSDT",timestamp=ts,decision_time=ts,
        point_in_time_available_at=ts,version="v1",feature_version="f1",
        numeric={"x":1},categorical={"regime":"trend"},availability={"x":True})
    b=StateVector.build(symbol="BTCUSDT",timestamp=ts,decision_time=ts,
        point_in_time_available_at=ts,version="v1",feature_version="f1",
        numeric={"x":1},categorical={"regime":"range"},availability={"x":True})
    assert a.fingerprint!=b.fingerprint
def test_state_vector_rejects_future_pit():
    ts=datetime(2026,1,1,tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        StateVector.build(symbol="BTCUSDT",timestamp=ts,decision_time=ts,
            point_in_time_available_at=ts+timedelta(seconds=1),version="v1",feature_version="f1")
