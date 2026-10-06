from datetime import datetime, timezone

from research_os.intelligence.models import AnalysisResult, EvidenceDirection
from research_os.intelligence.probability import ProbabilityResult
from research_os.notifications.telegram import TelegramFormatter
from research_os.pipeline.realtime import RealtimeSignalPipeline
from research_os.signals.engine import SignalEngine
from research_os.signals.guard import SignalGuard
from research_os.signals.models import SignalDirection


class FixedAnalyzer:
    def analyze(self, state):
        return AnalysisResult(
            "BTCUSDT",
            state.timestamp,
            EvidenceDirection.BULLISH,
            (),
            0.8,
            0.1,
            0,
            True,
            "deterministic test analysis",
        )


class FixedProbability:
    def predict(self, analysis):
        return ProbabilityResult(
            analysis.symbol,
            analysis.timestamp,
            0.80,
            0.10,
            0.10,
        )


def state():
    from research_os.market.state_vector import MarketStateVector

    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    return MarketStateVector.build(
        "BTCUSDT",
        now,
        now,
        now,
        {"return_1": 0.01, "return_5": 0.02},
        {"return_1": True, "return_5": True},
        {},
    )


def test_realtime_pipeline_marks_sent_only_after_default_emission():
    guard = SignalGuard()
    pipeline = RealtimeSignalPipeline(
        FixedAnalyzer(),
        FixedProbability(),
        SignalEngine(),
        TelegramFormatter(),
        guard,
    )

    signal, message = pipeline.evaluate(state(), 100.0, 2.0)

    assert signal.direction is SignalDirection.LONG
    assert message is not None
    assert guard.last_key is not None
    assert guard.last_sent_at == signal.timestamp


def test_realtime_pipeline_can_defer_cooldown_commit():
    guard = SignalGuard()
    pipeline = RealtimeSignalPipeline(
        FixedAnalyzer(),
        FixedProbability(),
        SignalEngine(),
        TelegramFormatter(),
        guard,
    )

    signal, message = pipeline.evaluate(state(), 100.0, 2.0, mark_sent=False)

    assert signal.direction is SignalDirection.LONG
    assert message is not None
    assert guard.last_key is None
    assert guard.last_sent_at is None

    guard.mark_sent(signal)
    assert guard.last_key is not None
    assert guard.last_sent_at == signal.timestamp


def test_deferred_signal_can_be_rejected_before_cooldown_is_committed():
    guard = SignalGuard()
    pipeline = RealtimeSignalPipeline(
        FixedAnalyzer(),
        FixedProbability(),
        SignalEngine(),
        TelegramFormatter(),
        guard,
    )

    signal, message = pipeline.evaluate(state(), 100.0, 2.0, mark_sent=False)

    assert signal.direction is SignalDirection.LONG
    assert message is not None
    ok, reasons = guard.validate(signal)
    assert ok
    assert reasons == ()
    assert guard.last_key is None
