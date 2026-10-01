from __future__ import annotations
from research_os.intelligence.models import AnalysisResult, Evidence, EvidenceDirection
from research_os.market.state_vector import MarketStateVector

class MarketAnalyzer:
    """Converts available MSV features into auditable evidence; no probability is produced."""
    version="analysis-v1"

    def analyze(self, state: MarketStateVector) -> AnalysisResult:
        ev=[]

        def add(name, direction, value, strength, reason):
            if state.availability.get(name, False) and value is not None:
                ev.append(Evidence(
                    name,
                    direction,
                    min(1.0, max(0.0, strength)),
                    value,
                    state.timestamp,
                    "msv",
                    1.0,
                    reason,
                ))

        r=state.values.get("return_1")
        if r is not None:
            add(
                "return_1",
                EvidenceDirection.BULLISH if r > 0 else EvidenceDirection.BEARISH,
                r,
                min(abs(r) / 0.01, 1),
                "positive/negative short-term return",
            )

        r5=state.values.get("return_5")
        if r5 is not None:
            add(
                "return_5",
                EvidenceDirection.BULLISH if r5 > 0 else EvidenceDirection.BEARISH,
                r5,
                min(abs(r5) / 0.03, 1),
                "positive/negative multi-bar return",
            )

        # Higher-timeframe evidence stays separate from base 1m/5m evidence.
        for timeframe, scale in (("15m", 0.01), ("1h", 0.02), ("4h", 0.04), ("1d", 0.08)):\n            name=f"tf_{timeframe}_return_1"\n            value=state.values.get(name)\n            if state.availability.get(name, False) and value is not None and value != 0:\n                add(name, EvidenceDirection.BULLISH if value > 0 else EvidenceDirection.BEARISH, value, min(abs(value) / scale, 1.0), f"{timeframe} directional context")\n\n        obi=state.values.get("orderbook_imbalance")
        if obi is not None and state.availability.get("orderbook_imbalance", False):
            if obi > 0.05:
                add("orderbook_imbalance", EvidenceDirection.BULLISH, obi, min(abs(obi), 1.0), "bid depth exceeds ask depth")
            elif obi < -0.05:
                add("orderbook_imbalance", EvidenceDirection.BEARISH, obi, min(abs(obi), 1.0), "ask depth exceeds bid depth")

        flow=state.values.get("orderflow_imbalance")
        if state.availability.get("orderflow_imbalance", False) and flow is not None:
            if flow > 0.10:
                add("orderflow_imbalance", EvidenceDirection.BULLISH, flow, min(abs(flow), 1.0), "aggressive buy volume exceeds sell volume")
            elif flow < -0.10:
                add("orderflow_imbalance", EvidenceDirection.BEARISH, flow, min(abs(flow), 1.0), "aggressive sell volume exceeds buy volume")

        divergence=state.values.get("orderflow_price_delta_divergence")
        if state.availability.get("orderflow_price_delta_divergence", False) and divergence:
            add("orderflow_price_delta_divergence", EvidenceDirection.BULLISH if divergence > 0 else EvidenceDirection.BEARISH, divergence, 0.5, "price and cumulative delta moved in opposite directions")

        absorption=state.values.get("orderflow_absorption")
        if state.availability.get("orderflow_absorption", False) and absorption is not None and absorption >= 0.20:
            add("orderflow_absorption", EvidenceDirection.NEUTRAL, absorption, min(absorption, 1.0), "large-trade concentration with directional flow")

        oi_div=state.values.get("derivatives_price_oi_divergence")
        if state.availability.get("derivatives_price_oi_divergence", False) and oi_div:
            add("derivatives_price_oi_divergence", EvidenceDirection.NEUTRAL, oi_div, 0.5, "price and open interest moved in opposite directions; directional meaning requires validation")

        liq=state.values.get("derivatives_liquidation_imbalance")
        if state.availability.get("derivatives_liquidation_imbalance", False) and liq is not None and abs(liq) > 0.20:
            add("derivatives_liquidation_imbalance", EvidenceDirection.NEUTRAL, liq, min(abs(liq),1.0), "recent long/short liquidation imbalance is contextual")

        oi_change=state.values.get("derivatives_oi_change")
        if state.availability.get("derivatives_oi_change", False) and oi_change is not None:
            add("derivatives_oi_change", EvidenceDirection.NEUTRAL, oi_change, min(abs(oi_change)/0.05,1.0), "open interest change is contextual, not directional alone")

        vol=state.values.get("realized_vol")
        if vol is not None:
            add("realized_vol", EvidenceDirection.NEUTRAL, vol, min(vol / 0.02, 1), "volatility is state information, not direction")

        bull=sum(e.strength * e.reliability for e in ev if e.direction is EvidenceDirection.BULLISH)
        bear=sum(e.strength * e.reliability for e in ev if e.direction is EvidenceDirection.BEARISH)
        bullish=[e for e in ev if e.direction is EvidenceDirection.BULLISH]
        bearish=[e for e in ev if e.direction is EvidenceDirection.BEARISH]
        has_conflict=bool(bullish and bearish)

        if not bullish and not bearish:
            direction=EvidenceDirection.NEUTRAL
        elif has_conflict:
            direction=EvidenceDirection.CONFLICTING
        else:
            direction=EvidenceDirection.BULLISH if bull > bear else EvidenceDirection.BEARISH

        conflicts=1 if has_conflict else 0
        directional=bool(bullish or bearish)
        sufficient=directional and all(state.availability.get(k, False) for k in ("return_1", "return_5"))
        reason=(
            "insufficient directional evidence"
            if not sufficient
            else "conflicting directional evidence"
            if direction is EvidenceDirection.CONFLICTING
            else "directional evidence aggregated from available features"
        )
        return AnalysisResult(
            state.symbol,
            state.timestamp,
            direction,
            tuple(ev),
            bull,
            bear,
            conflicts,
            sufficient,
            reason,
        )
