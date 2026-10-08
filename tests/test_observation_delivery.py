from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from research_os.intelligence.models import AnalysisResult, Evidence, EvidenceDirection
from research_os.intelligence.probability import ProbabilityResult
from research_os.notifications.telegram import TelegramFormatter
from research_os.pipeline.live import LiveSignalService
from research_os.signals.engine import SignalEngine

NOW = datetime(2026, 10, 9, tzinfo=UTC)


@pytest.mark.parametrize('direction,probability', [
    (EvidenceDirection.BULLISH, ProbabilityResult('BTCUSDT', NOW, .82, .08, .1)),
    (EvidenceDirection.BEARISH, ProbabilityResult('BTCUSDT', NOW, .08, .82, .1)),
])
def test_emitted_comment_contains_only_supporting_evidence(direction, probability):
    opposite = EvidenceDirection.BEARISH if direction is EvidenceDirection.BULLISH else EvidenceDirection.BULLISH
    reason = 'positive/negative short-term return'
    analysis = AnalysisResult('BTCUSDT', NOW, direction, (
        Evidence('return_1', direction, 1, .01, NOW, 'msv', reason=reason),
        Evidence('other', opposite, .1, .01, NOW, 'msv', reason='opposing argument'),
        Evidence('context', EvidenceDirection.NEUTRAL, .5, .1, NOW, 'msv', reason='neutral argument'),
    ), 3, 0, 0, True)
    signal = SignalEngine().build(analysis, probability, 100, 2)
    assert signal.direction.value in ('long', 'short')
    assert signal.rationale == (reason,)
    message = TelegramFormatter(observation=True).format(signal)
    assert 'Комментарий системы:' in message.text
    assert 'Движение цены' in message.text
    assert 'не вероятность успеха' in message.text
    assert 'opposing argument' not in message.text
    assert 'SL:' in message.text and 'TP1:' in message.text
    assert not message.buttons


def test_shadow_uses_observation_format_and_production_keeps_calibration_gate():
    service = LiveSignalService(settings=SimpleNamespace(environment='shadow'))
    assert service.pipeline.formatter.observation
    assert not service.pipeline.signal.require_calibrated_probability
    production = LiveSignalService(settings=SimpleNamespace(environment='production'))
    assert production.pipeline.signal.require_calibrated_probability
