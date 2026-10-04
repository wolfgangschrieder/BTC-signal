from __future__ import annotations
from dataclasses import dataclass
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.probability import ProbabilityEngine
from research_os.market.state_vector import MarketStateVector
from research_os.notifications.telegram import TelegramFormatter
from research_os.signals.engine import SignalEngine
from research_os.signals.guard import SignalGuard, SignalExecutionContext
from research_os.features.liquidity import LiquidityCluster
from research_os.pipeline.latency import LatencyTelemetry

@dataclass
class RealtimeSignalPipeline:
    analyzer: MarketAnalyzer
    probability: ProbabilityEngine
    signal: SignalEngine
    formatter: TelegramFormatter
    guard: SignalGuard
    latency: LatencyTelemetry | None = None

    def evaluate(self, state: MarketStateVector, price: float, atr: float|None, context: SignalExecutionContext|None=None, liquidity_clusters: tuple[LiquidityCluster,...]=()):
        if self.latency is None:
            analysis=self.analyzer.analyze(state)
            probability=self.probability.predict(analysis)
            signal=self.signal.build(analysis,probability,price,atr,liquidity_clusters=liquidity_clusters)
            allowed=self.guard.allow(signal,context)
        else:
            with self.latency.timer("analysis"):
                analysis=self.analyzer.analyze(state)
            with self.latency.timer("probability"):
                probability=self.probability.predict(analysis)
            with self.latency.timer("signal"):
                signal=self.signal.build(analysis,probability,price,atr,liquidity_clusters=liquidity_clusters)
            with self.latency.timer("guard"):
                allowed=self.guard.allow(signal,context)

        message=None
        if allowed:
            message=self.formatter.format(signal)
            # Guard cooldown is stateful policy, so a successful emission must
            # atomically advance its suppression state in the same pipeline that
            # performed validation. Previously mark_sent() was never called.
            self.guard.mark_sent(signal)
        return signal,message
