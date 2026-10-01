from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class RiskPolicy:
    max_leverage: float=5.0
    min_leverage: float=1.0
    max_account_risk: float=0.01
    target_risk: float=0.005

class RiskEngine:
    version="risk-v1"
    def __init__(self, policy: RiskPolicy=RiskPolicy()): self.policy=policy
    def recommended_leverage(self, entry: float, stop: float, probability: float) -> float:
        if entry<=0 or stop<=0 or not 0<=probability<=1: raise ValueError("invalid risk inputs")
        stop_distance=abs(entry-stop)/entry
        if stop_distance<=0: return self.policy.min_leverage
        # Leverage is constrained by stop distance and risk budget; probability does not directly map to leverage.
        lev=self.policy.target_risk/stop_distance
        return max(self.policy.min_leverage,min(self.policy.max_leverage,lev))
