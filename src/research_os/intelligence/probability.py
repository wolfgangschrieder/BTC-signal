from __future__ import annotations
from dataclasses import dataclass
from math import exp, log
from research_os.intelligence.models import AnalysisResult, EvidenceDirection

@dataclass(frozen=True)
class ProbabilityResult:
    symbol: str
    timestamp: object
    long: float
    short: float
    no_signal: float
    model_version: str = "probability-v1"

class ProbabilityEngine:
    """Transparent evidence-to-probability mapping. Not a calibrated production model yet."""
    version="probability-v1"
    def __init__(self, min_directional_score: float = 0.15, temperature: float = 1.0):
        if min_directional_score < 0 or temperature <= 0: raise ValueError("invalid probability parameters")
        self.min_directional_score=min_directional_score
        self.temperature=temperature

    def predict(self, analysis: AnalysisResult) -> ProbabilityResult:
        b=max(0.0, analysis.bullish_score); s=max(0.0, analysis.bearish_score)
        if not analysis.sufficient_data or (b+s) < self.min_directional_score or analysis.direction is EvidenceDirection.CONFLICTING:
            return ProbabilityResult(analysis.symbol,analysis.timestamp,0.0,0.0,1.0,self.version)
        # Softmax over directional evidence, with an explicit abstention mass.
        scale=max(self.temperature,1e-12)
        eb=exp(b/scale); es=exp(s/scale)
        raw=eb+es
        directional=min(0.95, max(0.0, (b+s)/(b+s+1.0)))
        return ProbabilityResult(analysis.symbol,analysis.timestamp,
            directional*eb/raw, directional*es/raw, 1.0-directional,self.version)

@dataclass(frozen=True)
class CalibrationSample:
    predicted: float
    outcome: int

class CalibrationMetrics:
    @staticmethod
    def brier(samples: list[CalibrationSample]) -> float:
        if not samples: return 0.0
        return sum((x.predicted-x.outcome)**2 for x in samples)/len(samples)
    @staticmethod
    def log_loss(samples: list[CalibrationSample], eps: float=1e-15) -> float:
        if not samples: return 0.0
        total=0.0
        for x in samples:
            p=min(1-eps,max(eps,x.predicted))
            total += -(log(p) if x.outcome else log(1-p))
        return total/len(samples)
