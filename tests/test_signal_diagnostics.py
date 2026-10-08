from datetime import UTC, datetime

from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.probability import ProbabilityEngine
from research_os.market.state_vector import MarketStateVector
from research_os.research.signal_diagnostics import summarize


def row(values):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return {
        'symbol': 'BTCUSDT', 'timestamp': now, 'decision_time': now,
        'point_in_time_available_at': now, 'vector_version': 'msv-v2',
        'feature_version': 'features-v1', 'data_quality': {},
        'vector': {'values': values, 'availability': dict.fromkeys(values, True)},
    }



def test_reports_conflicts_and_threshold_without_inventing_outcomes():
    rows = [row({'return_1': .01, 'return_5': .03}),
            row({'return_1': .01, 'return_5': -.03}), row({})]
    result = summarize(rows, threshold=.3)
    assert result['states'] == 3
    assert result['analysis_directions'] == {'bullish': 1, 'conflicting': 1, 'neutral': 1}
    assert result['direction_candidates_above_threshold'] == 1
    state = MarketStateVector.build('BTCUSDT', rows[0]['timestamp'], rows[0]['decision_time'],
                                   rows[0]['point_in_time_available_at'],
                                   rows[0]['vector']['values'], rows[0]['vector']['availability'], {})
    expected = ProbabilityEngine().predict(MarketAnalyzer().analyze(state)).long
    assert result['directional_score']['max'] == expected
    assert summarize(rows)['direction_candidates_above_threshold'] == 0


def test_empty_and_single_state():
    assert summarize([])['directional_score']['max'] is None
    result = summarize([row({})])
    assert result['directional_score'] == {'median': 0, 'p90': 0, 'max': 0}
