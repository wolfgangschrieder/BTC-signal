from datetime import UTC, datetime, timedelta

from research_os.research.replay import ReplayCandle, ReplayEngine


class StubFeatures:
    version = "stub"

    def build(self, symbol, timestamp, closes, volumes, highs, lows):
        class Snapshot:
            features = ()

        return Snapshot()


class StubBuilder:
    def build(self, symbol, timestamp, pit, available_at, snapshot, extra):
        from types import SimpleNamespace

        return SimpleNamespace(values={})


class StubAnalyzer:
    version = "stub"

    def analyze(self, state):
        return state


class StubProbability:
    version = "stub"

    def predict(self, analysis):
        return object()


def candles(prices):
    t = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        ReplayCandle(t + timedelta(minutes=i), p, p + 0.2, p - 0.2, p, 1, t + timedelta(minutes=i))
        for i, p in enumerate(prices)
    ]


def test_replay_is_deterministic():
    data = candles([100, 100.1, 100.2, 100.3, 100.4, 100.5, 101, 101.2, 101.4, 101.6])
    e = ReplayEngine()
    assert e.run("BTCUSDT", data, "fixture-v1") == e.run("BTCUSDT", data, "fixture-v1")


def test_replay_uses_availability_as_decision_time():
    t = datetime(2026, 1, 1, tzinfo=UTC)
    data = [
        ReplayCandle(
            t + i * timedelta(minutes=1),
            100 + i,
            101 + i,
            99 + i,
            100 + i,
            1,
            t + i * timedelta(minutes=1) + timedelta(seconds=30),
        )
        for i in range(8)
    ]
    report = ReplayEngine().run("BTCUSDT", data)
    assert report.dataset_version == "replay-v1"


def test_replay_does_not_score_candles_observed_before_delayed_decision():
    from research_os.signals.models import SignalDirection

    class StubSignal:
        version = "stub"

        def build(self, analysis, probability, price, atr):
            class Levels:
                entry_min = 100.0
                entry_max = 100.0
                stop_loss = 99.0
                tp1 = 101.0

            class Signal:
                direction = SignalDirection.LONG
                probability = 0.8
                levels = Levels()

            return Signal()

    t = datetime(2026, 1, 1, tzinfo=UTC)
    data = [
        ReplayCandle(t, 100, 100, 100, 100, 1, t + timedelta(minutes=5)),
        ReplayCandle(t + timedelta(minutes=1), 100, 101, 99, 100, 1, t + timedelta(minutes=1)),
        ReplayCandle(t + timedelta(minutes=2), 100, 100, 100, 100, 1, t + timedelta(minutes=2)),
        ReplayCandle(t + timedelta(minutes=3), 101, 101, 101, 101, 1, t + timedelta(minutes=3)),
        ReplayCandle(t + timedelta(minutes=4), 100, 100, 100, 100, 1, t + timedelta(minutes=4)),
        ReplayCandle(t + timedelta(minutes=5), 100, 100, 100, 100, 1, t + timedelta(minutes=5)),
        ReplayCandle(t + timedelta(minutes=6), 100, 100, 100, 100, 1, t + timedelta(minutes=6)),
        ReplayCandle(t + timedelta(minutes=7), 101, 101, 101, 101, 1, t + timedelta(minutes=7)),
    ]
    engine = ReplayEngine(
        feature_engine=StubFeatures(),
        builder=StubBuilder(),
        analyzer=StubAnalyzer(),
        probability=StubProbability(),
        signal_engine=StubSignal(),
        horizon_minutes=2,
    )
    report = engine.run("BTCUSDT", data)
    assert report.results
    first = report.results[0]
    assert first.timestamp == t + timedelta(minutes=5)
    assert first.outcome_status == "win"


def test_replay_signal_price_uses_latest_pit_available_close():
    from research_os.signals.models import SignalDirection

    class CaptureSignal:
        version = "capture"

        def __init__(self):
            self.prices = []

        def build(self, analysis, probability, price, atr):
            self.prices.append(price)

            class Levels:
                entry_min = price
                entry_max = price
                stop_loss = price - 1
                tp1 = price + 1

            class Signal:
                direction = SignalDirection.LONG
                probability = 0.8
                levels = Levels()

            return Signal()

    t = datetime(2026, 1, 1, tzinfo=UTC)
    data = [
        ReplayCandle(t, 100, 100, 100, 100, 1, t),
        ReplayCandle(t + timedelta(minutes=1), 101, 101, 101, 101, 1, t + timedelta(minutes=5)),
        ReplayCandle(t + timedelta(minutes=2), 102, 102, 102, 102, 1, t + timedelta(minutes=2)),
        ReplayCandle(t + timedelta(minutes=3), 103, 103, 103, 103, 1, t + timedelta(minutes=3)),
        ReplayCandle(t + timedelta(minutes=4), 104, 104, 104, 104, 1, t + timedelta(minutes=4)),
        ReplayCandle(t + timedelta(minutes=5), 105, 105, 105, 105, 1, t + timedelta(minutes=5)),
        ReplayCandle(t + timedelta(minutes=6), 106, 106, 106, 106, 1, t + timedelta(minutes=6)),
    ]
    capture = CaptureSignal()
    engine = ReplayEngine(
        feature_engine=StubFeatures(),
        builder=StubBuilder(),
        analyzer=StubAnalyzer(),
        probability=StubProbability(),
        signal_engine=capture,
        horizon_minutes=1,
    )
    engine.run("BTCUSDT", data)
    assert capture.prices
    assert capture.prices[0] == 105.0


def test_replay_marks_same_candle_tp_and_sl_as_ambiguous():
    from types import SimpleNamespace

    from research_os.signals.models import SignalDirection

    t = datetime(2026, 1, 1, tzinfo=UTC)
    signal = SimpleNamespace(
        direction=SignalDirection.LONG,
        levels=SimpleNamespace(entry_min=100.0, entry_max=100.0, stop_loss=99.0, tp1=101.0),
    )
    data = [
        ReplayCandle(t, 100, 100, 100, 100, 1, t),
        ReplayCandle(t + timedelta(minutes=1), 100, 100, 100, 100, 1, t + timedelta(minutes=1)),
        ReplayCandle(t + timedelta(minutes=2), 100, 102, 98, 100, 1, t + timedelta(minutes=2)),
    ]
    engine = ReplayEngine(horizon_minutes=5)
    status, outcome, ret = engine._future_outcome(signal, data, t)
    assert status == "ambiguous"
    assert outcome is None
    assert ret is None


def test_replay_applies_fee_and_slippage_to_realized_return():
    from types import SimpleNamespace

    from research_os.signals.models import SignalDirection

    t = datetime(2026, 1, 1, tzinfo=UTC)
    signal = SimpleNamespace(
        direction=SignalDirection.LONG,
        levels=SimpleNamespace(entry_min=100.0, entry_max=100.0, stop_loss=99.0, tp1=101.0),
    )
    data = [
        ReplayCandle(t, 100, 100, 100, 100, 1, t),
        ReplayCandle(t + timedelta(minutes=1), 100, 100, 100, 100, 1, t + timedelta(minutes=1)),
        ReplayCandle(t + timedelta(minutes=2), 101, 101, 101, 101, 1, t + timedelta(minutes=2)),
    ]
    engine = ReplayEngine(horizon_minutes=5, fee_bps=10.0, slippage_bps=10.0)
    status, outcome, ret = engine._future_outcome(signal, data, t)
    assert status == "win"
    assert outcome == 1
    assert ret is not None
    assert ret < 0.01


def test_replay_can_build_decision_from_delayed_pit_candle():
    from research_os.signals.models import SignalDirection

    class CaptureSignal:
        version = "capture"

        def __init__(self):
            self.prices = []

        def build(self, analysis, probability, price, atr):
            self.prices.append(price)

            class Levels:
                entry_min = price
                entry_max = price
                stop_loss = price - 1
                tp1 = price + 1

            class Signal:
                direction = SignalDirection.LONG
                probability = 0.8
                levels = Levels()

            return Signal()

    t = datetime(2026, 1, 1, tzinfo=UTC)
    data = [
        ReplayCandle(t, 100, 100, 100, 100, 1, t),
        ReplayCandle(t + timedelta(minutes=1), 101, 101, 101, 101, 1, t + timedelta(minutes=5)),
        ReplayCandle(t + timedelta(minutes=2), 102, 102, 102, 102, 1, t + timedelta(minutes=2)),
        ReplayCandle(t + timedelta(minutes=3), 103, 103, 103, 103, 1, t + timedelta(minutes=3)),
        ReplayCandle(t + timedelta(minutes=4), 104, 104, 104, 104, 1, t + timedelta(minutes=4)),
        ReplayCandle(t + timedelta(minutes=5), 105, 105, 105, 105, 1, t + timedelta(minutes=5)),
        ReplayCandle(t + timedelta(minutes=6), 106, 106, 106, 106, 1, t + timedelta(minutes=6)),
    ]
    capture = CaptureSignal()
    engine = ReplayEngine(
        feature_engine=StubFeatures(),
        builder=StubBuilder(),
        analyzer=StubAnalyzer(),
        probability=StubProbability(),
        signal_engine=capture,
        horizon_minutes=1,
    )
    report = engine.run("BTCUSDT", data)
    assert report.results
    assert capture.prices[0] == 105.0


def test_replay_report_exposes_ambiguous_and_unresolved_without_scoring_them():
    from types import SimpleNamespace

    from research_os.signals.models import SignalDirection

    t = datetime(2026, 1, 1, tzinfo=UTC)
    signal = SimpleNamespace(
        direction=SignalDirection.LONG,
        probability=0.8,
        levels=SimpleNamespace(entry_min=100.0, entry_max=100.0, stop_loss=99.0, tp1=101.0),
    )
    data = candles([100] * 6) + [
        ReplayCandle(t + timedelta(minutes=6), 100, 102, 98, 100, 1, t + timedelta(minutes=6)),
        ReplayCandle(t + timedelta(minutes=7), 100, 102, 98, 100, 1, t + timedelta(minutes=7)),
        ReplayCandle(t + timedelta(minutes=8), 100, 100, 100, 100, 1, t + timedelta(minutes=8)),
    ]
    engine = ReplayEngine(
        feature_engine=StubFeatures(),
        builder=StubBuilder(),
        analyzer=StubAnalyzer(),
        probability=StubProbability(),
        signal_engine=SimpleNamespace(version="stub", build=lambda *args: signal),
        horizon_minutes=2,
    )
    report = engine.run("BTCUSDT", data)
    assert report.results[0].outcome_status == "ambiguous"
    assert report.ambiguous == 1
    assert report.unresolved == report.signals
    assert report.resolved == report.wins == report.losses == 0
    assert report.win_rate is None


def test_replay_entry_gap_does_not_fill():
    from types import SimpleNamespace

    from research_os.signals.models import SignalDirection

    t = datetime(2026, 1, 1, tzinfo=UTC)
    signal = SimpleNamespace(
        direction=SignalDirection.LONG,
        levels=SimpleNamespace(entry_min=100.0, entry_max=100.0, stop_loss=99.0, tp1=101.0),
    )
    data = [
        ReplayCandle(t, 100, 100, 100, 100, 1, t),
        ReplayCandle(t + timedelta(minutes=1), 102, 103, 102, 103, 1, t + timedelta(minutes=1)),
    ]
    engine = ReplayEngine(horizon_minutes=5)
    status, outcome, ret = engine._future_outcome(signal, data, t)
    assert status == "expired"
    assert outcome is None
    assert ret is None


def test_replay_short_same_candle_tp_and_sl_is_ambiguous():
    from types import SimpleNamespace

    from research_os.signals.models import SignalDirection

    t = datetime(2026, 1, 1, tzinfo=UTC)
    signal = SimpleNamespace(
        direction=SignalDirection.SHORT,
        levels=SimpleNamespace(entry_min=100.0, entry_max=100.0, stop_loss=101.0, tp1=99.0),
    )
    data = [
        ReplayCandle(t, 100, 100, 100, 100, 1, t),
        ReplayCandle(t + timedelta(minutes=1), 100, 100, 100, 100, 1, t + timedelta(minutes=1)),
        ReplayCandle(t + timedelta(minutes=2), 100, 102, 98, 100, 1, t + timedelta(minutes=2)),
    ]
    engine = ReplayEngine(horizon_minutes=5)
    status, outcome, ret = engine._future_outcome(signal, data, t)
    assert status == "ambiguous"
    assert outcome is None
    assert ret is None


def test_replay_entry_candle_does_not_exit_same_candle():
    from datetime import datetime, timedelta
    from types import SimpleNamespace

    from research_os.research.replay import ReplayCandle, ReplayEngine
    from research_os.signals.models import SignalDirection

    t = datetime(2026, 1, 1, tzinfo=UTC)
    signal = SimpleNamespace(
        direction=SignalDirection.LONG,
        levels=SimpleNamespace(entry_min=100.0, entry_max=100.0, stop_loss=99.0, tp1=101.0),
    )
    data = [
        ReplayCandle(t, 100, 100, 100, 100, 1, t),
        ReplayCandle(t + timedelta(minutes=1), 100, 102, 100, 102, 1, t + timedelta(minutes=1)),
    ]
    engine = ReplayEngine(horizon_minutes=2)
    status, outcome, ret = engine._future_outcome(signal, data, t)
    assert status == "expired"
    assert outcome is None
    assert ret is None


def test_replay_entry_candle_with_tp_and_sl_waits_for_next_candle():
    from datetime import datetime, timedelta
    from types import SimpleNamespace

    from research_os.research.replay import ReplayCandle, ReplayEngine
    from research_os.signals.models import SignalDirection

    t = datetime(2026, 1, 1, tzinfo=UTC)
    signal = SimpleNamespace(
        direction=SignalDirection.LONG,
        levels=SimpleNamespace(entry_min=100.0, entry_max=100.0, stop_loss=99.0, tp1=101.0),
    )
    data = [
        ReplayCandle(t, 100, 100, 100, 100, 1, t),
        ReplayCandle(t + timedelta(minutes=1), 100, 102, 98, 100, 1, t + timedelta(minutes=1)),
    ]
    engine = ReplayEngine(horizon_minutes=2)
    status, outcome, ret = engine._future_outcome(signal, data, t)
    assert status == "expired"
    assert outcome is None
    assert ret is None


def test_replay_excludes_future_event_even_with_early_availability():
    from types import SimpleNamespace

    from research_os.signals.models import SignalDirection

    t = datetime(2026, 1, 1, tzinfo=UTC)
    data = candles([100, 101, 102, 103, 104, 105]) + [
        ReplayCandle(t + timedelta(minutes=10), 999, 999, 999, 999, 1, t + timedelta(minutes=5)),
    ]
    prices = []

    def capture(analysis, probability, price, atr):
        prices.append(price)
        return SimpleNamespace(direction=SignalDirection.NONE)

    engine = ReplayEngine(
        feature_engine=StubFeatures(),
        builder=StubBuilder(),
        analyzer=StubAnalyzer(),
        probability=StubProbability(),
        signal_engine=SimpleNamespace(version="capture", build=capture),
    )
    engine.run("BTCUSDT", data)
    assert prices == [105]
