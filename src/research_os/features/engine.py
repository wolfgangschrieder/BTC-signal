from __future__ import annotations
from dataclasses import dataclass
from research_os.market.types import OrderbookState, OrderflowState
from research_os.features.liquidity import LiquidityEngine, LiquidityState
from research_os.features.derivatives import DerivativesState

@dataclass(slots=True, frozen=True)
class FeatureSnapshot:
    timestamp: object
    numeric: dict[str,float|None]
    availability: dict[str,bool]

class FeatureEngine:
    __slots__=("liquidity",)
    def __init__(self, liquidity_levels: int=5):
        self.liquidity=LiquidityEngine(liquidity_levels)

    def build(self, *, orderflow: OrderflowState|None=None,
              orderbook: OrderbookState|None=None,
              derivatives: DerivativesState|None=None) -> FeatureSnapshot:
        timestamp=(orderbook.timestamp if orderbook is not None else
                   orderflow.timestamp if orderflow is not None else
                   derivatives.timestamp if derivatives is not None else None)
        if timestamp is None: raise ValueError("at least one feature source is required")
        numeric={}; availability={}
        if orderflow is not None:
            numeric.update({
                "orderflow.buy_volume":orderflow.buy_volume,
                "orderflow.sell_volume":orderflow.sell_volume,
                "orderflow.delta":orderflow.delta,
                "orderflow.cumulative_delta":orderflow.cumulative_delta,
                "orderflow.large_trade_share":orderflow.large_trade_share,
            })
            availability.update({f"orderflow.{k}":v is not None for k,v in {
                "buy_volume":orderflow.buy_volume,"sell_volume":orderflow.sell_volume,
                "delta":orderflow.delta,"cumulative_delta":orderflow.cumulative_delta,
                "large_trade_share":orderflow.large_trade_share}.items()})
        if orderbook is not None:
            liq=self.liquidity.calculate(orderbook)
            numeric.update({"liquidity.bid_depth":liq.bid_depth,"liquidity.ask_depth":liq.ask_depth,
                            "liquidity.imbalance":liq.imbalance,"liquidity.spread":liq.spread})
            availability.update({"liquidity.valid":liq.valid,"liquidity.spread":liq.spread is not None})
        if derivatives is not None:
            numeric.update({"derivatives.funding_rate":derivatives.funding_rate,
                            "derivatives.open_interest":derivatives.open_interest,
                            "derivatives.open_interest_change":derivatives.open_interest_change,
                            "derivatives.liquidation_delta":derivatives.liquidation_delta})
            availability.update({"derivatives.funding_rate":derivatives.funding_rate is not None,
                                 "derivatives.open_interest":derivatives.open_interest is not None,
                                 "derivatives.open_interest_change":derivatives.open_interest_change is not None,
                                 "derivatives.liquidation_delta":derivatives.liquidation_delta is not None})
        return FeatureSnapshot(timestamp,numeric,availability)
