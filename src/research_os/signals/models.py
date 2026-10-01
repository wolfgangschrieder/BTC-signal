from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import hashlib

class SignalDirection(str,Enum):
    LONG="long"; SHORT="short"; NONE="none"

@dataclass(frozen=True)
class SignalLevels:
    entry_min: float; entry_max: float; stop_loss: float; tp1: float; tp2: float; tp3: float; rr_tp1: float; rr_tp2: float; rr_tp3: float
    def __post_init__(self):
        if not all(v>0 for v in (self.entry_min,self.entry_max,self.stop_loss,self.tp1,self.tp2,self.tp3)): raise ValueError("signal prices must be positive")
        if self.entry_min>self.entry_max: raise ValueError("entry_min must not exceed entry_max")

@dataclass(frozen=True)
class SignalResult:
    symbol: str; timestamp: datetime; direction: SignalDirection; probability: float; no_signal_probability: float; levels: SignalLevels|None; expected_value: float; leverage: float; rationale: tuple[str,...]; risks: tuple[str,...]; model_version: str="signal-v1"
    @property
    def signal_id(self)->str:
        raw=f"{self.symbol}|{self.direction.value}|{self.timestamp.isoformat()}|{self.model_version}".encode()
        return hashlib.sha256(raw).hexdigest()[:32]
