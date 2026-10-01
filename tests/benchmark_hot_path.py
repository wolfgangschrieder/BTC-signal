from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from time import perf_counter_ns

from research_os.exchanges.bybit.normalizer import BybitNormalizer
from research_os.exchanges.bybit.orderbook import OrderBook
from research_os.features.engine import FeatureEngine
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.probability import ProbabilityEngine
from research_os.market.state_builder import MarketStateBuilder
from research_os.pipeline.realtime import RealtimeSignalPipeline
from research_os.notifications.telegram import TelegramFormatter
from research_os.signals.engine import SignalEngine
from research_os.signals.guard import SignalExecutionContext, SignalGuard


def percentile(samples, q):
    xs = sorted(samples)
    if not xs:
        raise ValueError("cannot calculate percentile of empty samples")
    if q <= 0.0:
        return xs[0]
    index = min(len(xs) - 1, int(__import__("math").ceil(q * len(xs))) - 1)
    return xs[index]


def summarize(samples):
    return {
        "count": len(samples),
        "min_ms": min(samples),
        "p50_ms": percentile(samples, 0.50),
        "p95_ms": percentile(samples, 0.95),
        "p99_ms": percentile(samples, 0.99),
        "max_ms": max(samples),
    }


def timed(fn, iterations, warmup):
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(iterations):
        start = perf_counter_ns()
        fn()
        samples.append((perf_counter_ns() - start) / 1_000_000.0)
    return summarize(samples)


def run(iterations=20_000, warmup=1_000):
    symbol = "BTCUSDT"
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closes = [100_000.0 + i * 2.0 + (i % 7) * 0.5 for i in range(200)]
    highs = [x + 20.0 for x in closes]
    lows = [x - 20.0 for x in closes]

    book = OrderBook(symbol, max_levels=50)
    bids = [[str(100_000.0 - i), str(1.0 + i / 100)] for i in range(50)]
    asks = [[str(100_001.0 + i), str(1.0 + i / 100)] for i in range(50)]
    book.restore_snapshot(bids, asks, 1, 1, int(timestamp.timestamp() * 1000))
    book_state = book.state

    feature_engine = FeatureEngine()
    snapshot = feature_engine.build(symbol, timestamp, closes, highs=highs, lows=lows, orderbook=book_state)
    state_builder = MarketStateBuilder()
    state = state_builder.build(symbol, timestamp, timestamp, timestamp, snapshot)

    analyzer = MarketAnalyzer()
    probability_engine = ProbabilityEngine()
    signal_engine = SignalEngine()
    guard = SignalGuard()
    context = SignalExecutionContext(latency_ms=1.0, spread_bps=0.1, orderbook_valid=True, orderbook_age_ms=1)
    pipeline = RealtimeSignalPipeline(
        analyzer, probability_engine, signal_engine, TelegramFormatter(), guard
    )

    delta = {
        "topic": "orderbook.50.BTCUSDT",
        "type": "delta",
        "ts": int(timestamp.timestamp() * 1000),
        "data": {
            "s": symbol, "u": 2, "seq": 2,
            "b": [["100000", "1.25"]], "a": [["100001", "1.10"]],
        },
    }

    normalize_message = {
        "topic": "orderbook.50.BTCUSDT",
        "type": "delta",
        "ts": int(timestamp.timestamp() * 1000),
        "data": {
            "s": symbol, "u": 2, "seq": 2,
            "b": [["100000", "1.25"]], "a": [["100001", "1.10"]],
        },
    }

    def apply_delta():
        delta["data"]["u"] += 1
        delta["data"]["seq"] += 1
        return book.apply(delta)

    analysis = analyzer.analyze(state)
    probability = probability_engine.predict(analysis)
    atr = next((f.value for f in snapshot.features if f.name == "atr_14"), 20.0)
    signal = signal_engine.build(analysis, probability, closes[-1], atr)

    stages = {
        "orderbook_state": timed(lambda: book.state, iterations, warmup),
        "orderbook_apply": timed(apply_delta, iterations, warmup),
        "orderbook_normalize": timed(
            lambda: BybitNormalizer.orderbook(normalize_message, ingestion_time=timestamp),
            iterations, warmup,
        ),
        "feature_build": timed(
            lambda: feature_engine.build(
                symbol, timestamp, closes, highs=highs, lows=lows, orderbook=book_state
            ),
            iterations, warmup,
        ),
        "state_build": timed(
            lambda: state_builder.build(symbol, timestamp, timestamp, timestamp, snapshot),
            iterations, warmup,
        ),
        "analysis": timed(lambda: analyzer.analyze(state), iterations, warmup),
        "probability": timed(lambda: probability_engine.predict(analysis), iterations, warmup),
        "signal": timed(
            lambda: signal_engine.build(analysis, probability, closes[-1], atr),
            iterations, warmup,
        ),
        "guard": timed(lambda: guard.validate(signal, context), iterations, warmup),
        "end_to_end": timed(
            lambda: pipeline.evaluate(state, closes[-1], atr, context=context),
            iterations, warmup,
        ),
    }
    return {
        "benchmark": "btc-signal-hot-path",
        "symbol": symbol,
        "iterations": iterations,
        "warmup": warmup,
        "python": sys.version.split()[0],
        "stages": stages,
    }


def main():
    parser = argparse.ArgumentParser(description="Synthetic BTC hot-path benchmark; no network or database.")
    parser.add_argument("--iterations", type=int, default=20_000)
    parser.add_argument("--warmup", type=int, default=1_000)
    args = parser.parse_args()
    if args.iterations <= 0 or args.warmup < 0:
        raise SystemExit("iterations must be > 0 and warmup must be >= 0")
    print(json.dumps(run(args.iterations, args.warmup), indent=2))


if __name__ == "__main__":
    main()
