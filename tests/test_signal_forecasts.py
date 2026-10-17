from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from research_os.signals.forecast_evaluator import forecast_metrics, SignalForecastEvaluator


def test_direction_is_independent_of_unreachable_entry():
    # No reference to trade levels: a rising market is correct LONG even if no fill.
    candles = [{"high":110,"low":101,"close":108}]
    ret,mfe,mae = forecast_metrics("long",100,candles)
    assert ret == pytest.approx(.08)
    assert mfe == pytest.approx(.10)
    assert mae == 0
    assert forecast_metrics("short",100,candles)[0] == pytest.approx(-.08)


def test_short_excursions_and_flat_endpoint():
    ret,mfe,mae = forecast_metrics("short",100,[{"high":103,"low":90,"close":100}])
    assert ret == 0
    assert mfe == pytest.approx(.10)
    assert mae == pytest.approx(-.03)


def test_future_labels_include_resolved_execution_and_require_full_data():
    now = datetime(2026,1,2,tzinfo=UTC)
    session = MagicMock()
    SignalForecastEvaluator().resolve(session,now)
    queries = [str(c.args[0]) for c in session.execute.call_args_list]
    assert "ON CONFLICT DO NOTHING" in queries[0]
    assert "s.status" not in queries[1]


def test_gap_waits_then_becomes_insufficient_instead_of_wrong_direction():
    decision = datetime(2026,1,1,tzinfo=UTC)
    row = {"signal_id":"s","symbol":"TEST","direction":"long","signal_time":decision,"horizon_minutes":15}
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.side_effect = [[row], []]
    session.execute.return_value.mappings.return_value.first.return_value = None
    SignalForecastEvaluator().resolve(session,decision+timedelta(hours=25))
    params = session.execute.call_args_list[-1].args[1]
    assert params["status"] == "insufficient_data"
    assert params["ret"] is None
