from __future__ import annotations
from dataclasses import dataclass
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.probability import ProbabilityEngine
from research_os.market.state_vector import MarketStateVector
from research_os.notifications.telegram import TelegramFormatter
from research_os.signals.engine import SignalEngine
from research_os.signals.guard import SignalGuard

@dataclass
class RealtimeSignalPipeline:
    analyzer: MarketAnalyzer
    probability: ProbabilityEngine
    signal: SignalEngine
    formatter: TelegramFormatter
    guard: SignalGuard

    def evaluate(self, state: MarketStateVector, price: float, atr: float|None):
        analysis=self.analyzer.analyze(state)
        probability=self.probability.predict(analysis)
        signal=self.signal.build(analysis,probability,price,atr)
        message=None
        if self.guard.allow(signal):
            message=self.formatter.format(signal)
        return signal,message
