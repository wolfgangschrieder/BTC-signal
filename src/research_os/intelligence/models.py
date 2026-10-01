from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class EvidenceDirection(str, Enum):
    BULLISH="bullish"; BEARISH="bearish"; NEUTRAL="neutral"; CONFLICTING="conflicting"

@dataclass(frozen=True)
class Evidence:
    feature: str
    direction: EvidenceDirection
    strength: float
    value: float | None
    timestamp: datetime
    source: str
    reliability: float = 1.0
    reason: str = ""
    def __post_init__(self):
        if not 0 <= self.strength <= 1: raise ValueError("strength must be in [0,1]")
        if not 0 <= self.reliability <= 1: raise ValueError("reliability must be in [0,1]")

@dataclass(frozen=True)
class AnalysisResult:
    symbol: str
    timestamp: datetime
    direction: EvidenceDirection
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)
    bullish_score: float = 0.0
    bearish_score: float = 0.0
    conflicts: int = 0
    sufficient_data: bool = True
    reason: str = ""
