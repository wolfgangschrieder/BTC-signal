from __future__ import annotations
from dataclasses import dataclass
import logging
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

    def evaluate(
        self,
        state: MarketStateVector,
        price: float,
        atr: float | None,
        context: SignalExecutionContext | None = None,
        liquidity_clusters: tuple[LiquidityCluster, ...] = (),
        mark_sent: bool = True,
    ):
        if self.latency is None:
            analysis = self.analyzer.analyze(state)
            probability = self.probability.predict(analysis)
            signal = self.signal.build(
                analysis, probability, price, atr, liquidity_clusters=liquidity_clusters
            )
            allowed = self.guard.allow(signal, context)
        else:
            with self.latency.timer("analysis"):
                analysis = self.analyzer.analyze(state)
            with self.latency.timer("probability"):
                probability = self.probability.predict(analysis)
            with self.latency.timer("signal"):
                signal = self.signal.build(
                    analysis, probability, price, atr, liquidity_clusters=liquidity_clusters
                )
            with self.latency.timer("guard"):
                allowed = self.guard.allow(signal, context)

        reasons = self.guard.validate(signal, context)[1] if not allowed else ()
        logging.getLogger(__name__).info(
            "Signal evaluation symbol=%s decision=%s analysis=%s sufficient=%s "
            "p_long=%.4f p_short=%.4f p_none=%.4f atr=%s direction=%s "
            "allowed=%s engine_reasons=%s guard_reasons=%s",
            state.symbol, state.decision_time.isoformat(), analysis.direction.value,
            analysis.sufficient_data, probability.long, probability.short,
            probability.no_signal, atr, signal.direction.value, allowed,
            signal.rationale if signal.direction.value == "none" else (), reasons,
        )
        message = None
        if allowed:
            message = self.formatter.format(signal)
            # Some callers need to persist/queue the emission before committing
            # the stateful cooldown. LiveSignalService uses this to avoid consuming
            # cooldown when the outcome queue is already full.
            if mark_sent:
                self.guard.mark_sent(signal)
        return signal, message
