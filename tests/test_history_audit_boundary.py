from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from research_os.pipeline.history import latest_closed_history_diagnostic

NOW = datetime(2026, 10, 20, 17, tzinfo=UTC)


def session_with(minutes):
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = (
        NOW-timedelta(minutes=min(minutes)) if minutes else None)
    session.execute.return_value.mappings.return_value.all.return_value = [
        {'event_time': NOW-timedelta(minutes=m), 'open': 100, 'high': 102,
         'low': 99, 'close': 101, 'volume': 1, 'raw_present': True, 'eligible': True}
        for m in minutes]
    return session


def test_delayed_latest_bar_retains_lag_and_restores_available_suffix():
    result = latest_closed_history_diagnostic(session_with([2, 3, 4]), 'BTCUSDT', NOW, 10)
    assert result['lag_seconds'] == 60
    assert result['latest_closed_at_utc'] == (NOW-timedelta(minutes=1)).isoformat()
    assert result['restoration']['restorable_contiguous_minutes'] == 3


def test_internal_gap_is_not_bridged_by_latest_bar_anchor():
    result = latest_closed_history_diagnostic(session_with([2, 3, 5]), 'BTCUSDT', NOW, 10)
    assert result['restoration']['restorable_contiguous_minutes'] == 2
    assert result['restoration']['boundary_reason'] == 'no_stored_bar_at_boundary'


def test_absent_closed_history_is_explicit():
    result = latest_closed_history_diagnostic(session_with([]), 'BTCUSDT', NOW, 10)
    assert result['status'] == 'no_closed_candle'
    assert result['restoration'] is None


def test_anchor_query_excludes_future_unclosed_and_unavailable_bars():
    session = session_with([])
    latest_closed_history_diagnostic(session, 'BTCUSDT', NOW, 10)
    query = str(session.execute.call_args.args[0])
    assert "event_time + interval '1 minute'<=:as_of" in query
    assert 'point_in_time_available_at<=:as_of' in query
    assert session.execute.call_args.args[1]['as_of'] == NOW


@pytest.mark.parametrize('limit', [0, 10081])
def test_invalid_limit_does_not_query(limit):
    session = MagicMock()
    with pytest.raises(ValueError):
        latest_closed_history_diagnostic(session, 'BTCUSDT', NOW, limit)
    session.execute.assert_not_called()
