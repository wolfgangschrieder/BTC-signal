from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import hashlib

class OutcomeStatus(StrEnum):
    PENDING="pending"; WIN="win"; LOSS="loss"; EXPIRED="expired"; AMBIGUOUS="ambiguous"

@dataclass(frozen=True)
class SignalIdentity:
    signal_id: str
    symbol: str
    direction: str
    signal_time: datetime

def make_signal_id(symbol,direction,signal_time,model_version):
    raw=f"{symbol}|{direction.value}|{signal_time.isoformat()}|{model_version}".encode()
    return hashlib.sha256(raw).hexdigest()[:32]

@dataclass(frozen=True)
class SignalOutcome:
    signal_id: str
    symbol: str
    direction: str
    signal_time: datetime
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    probability: float
    status: OutcomeStatus
    realized_return: float|None=None
    mfe: float|None=None
    mae: float|None=None
    resolved_at: datetime|None=None
    horizon_minutes: int|None=None
    reason: str|None=None
