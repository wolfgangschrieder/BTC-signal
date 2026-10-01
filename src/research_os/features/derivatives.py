from __future__ import annotations
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class DerivativesState:
    timestamp: object
    funding_rate: float|None
    open_interest: float|None
    open_interest_change: float|None
    liquidation_buy: float|None
    liquidation_sell: float|None
    valid: bool=True

    @property
    def liquidation_delta(self) -> float|None:
        if self.liquidation_buy is None or self.liquidation_sell is None:
            return None
        return self.liquidation_buy-self.liquidation_sell
