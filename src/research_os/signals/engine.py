from __future__ import annotations
from math import isfinite
from research_os.signals.execution import evaluate_candle
from research_os.intelligence.models import AnalysisResult, EvidenceDirection
from research_os.intelligence.probability import ProbabilityResult
from research_os.signals.models import SignalDirection, SignalLevels, SignalResult
from research_os.signals.risk import RiskEngine, LiquidityLevel
from research_os.features.liquidity import LiquidityCluster

class SignalEngine:
    version="signal-v4"

    def __init__(self, risk: RiskEngine | None = None, min_probability: float = .70, min_rr: float = 1.5, fee_bps: float = 0.0, slippage_bps: float = 0.0, require_calibrated_probability: bool = False):
        if any(not isfinite(v) or v < 0 for v in (fee_bps, slippage_bps)) or slippage_bps >= 10000:
            raise ValueError("execution costs must be finite and non-negative; slippage must be below 10000 bps")
        self.fee_bps=fee_bps
        self.slippage_bps=slippage_bps
        self.require_calibrated_probability=require_calibrated_probability
        self.risk=risk or RiskEngine()
        self.min_probability=min_probability
        self.min_rr=min_rr

    def build(self, analysis: AnalysisResult, probability: ProbabilityResult, price: float, atr: float | None = None, liquidity_levels: tuple[LiquidityLevel,...] = (), liquidity_clusters: tuple[LiquidityCluster,...] = ()) -> SignalResult:
        if price <= 0:
            raise ValueError("price must be positive")

        if self.require_calibrated_probability and not probability.calibrated:
            return SignalResult(
                analysis.symbol, analysis.timestamp, SignalDirection.NONE, 0.0,
                probability.no_signal, None, 0.0, 1.0,
                ("validated calibration required for production emission",), (), self.version,
            )

        direction=SignalDirection.NONE
        p=0.0

        if probability.long >= self.min_probability and probability.long > probability.short and analysis.direction is EvidenceDirection.BULLISH:
            direction,p=SignalDirection.LONG,probability.long
        elif probability.short >= self.min_probability and probability.short > probability.long and analysis.direction is EvidenceDirection.BEARISH:
            direction,p=SignalDirection.SHORT,probability.short

        if direction is SignalDirection.NONE:
            return SignalResult(
                analysis.symbol, analysis.timestamp, SignalDirection.NONE, 0.0,
                probability.no_signal, None, 0.0, 1.0,
                ("insufficient validated signal conditions",), (),
                self.version,
            )

        if atr is None or atr <= 0:
            return SignalResult(
                analysis.symbol, analysis.timestamp, SignalDirection.NONE, 0.0,
                probability.no_signal, None, 0.0, 1.0,
                ("volatility input required before signal emission",),
                ("missing/insufficient volatility input",),
                self.version,
            )

        entry_min,entry_max=price-0.15*atr,price+0.15*atr
        levels=self.risk.build_levels(direction.value,price,atr,liquidity_levels,liquidity_clusters)
        stop,t1,t2,t3=levels.stop_loss,levels.tp1,levels.tp2,levels.tp3

        risk=abs(price-stop)
        rr1=abs(t1-price)/risk
        rr2=abs(t2-price)/risk
        rr3=abs(t3-price)/risk

        if rr1 < self.min_rr:
            return SignalResult(
                analysis.symbol,analysis.timestamp,SignalDirection.NONE,0.0,
                probability.no_signal,None,0.0,1.0,
                ("TP1 risk/reward below policy threshold",),(),self.version
            )

        # Use the same adverse entry/exit fills and per-side fee convention as
        # recorded outcomes. This remains a binary TP1/SL proxy, not calibrated EV.
        long = direction is SignalDirection.LONG
        target_result = evaluate_candle(direction, entry_price=price, stop_loss=stop,
            take_profit=t1, high=t1 if long else price, low=price if long else t1,
            fee_bps=self.fee_bps, slippage_bps=self.slippage_bps)
        stop_result = evaluate_candle(direction, entry_price=price, stop_loss=stop,
            take_profit=t1, high=price if long else stop, low=stop if long else price,
            fee_bps=self.fee_bps, slippage_bps=self.slippage_bps)
        target_net, stop_net = target_result.realized_return, stop_result.realized_return
        if target_net is None or stop_net is None or target_net <= 0:
            return SignalResult(
                analysis.symbol, analysis.timestamp, SignalDirection.NONE, 0.0,
                probability.no_signal, None, 0.0, 1.0,
                ("TP1 does not cover assumed round-trip execution costs",), (), self.version)
        ev = (p * target_net + (1-p) * stop_net) / (risk / price)
        lev=self.risk.recommended_leverage(price,stop,p)
        evidence_direction = EvidenceDirection.BULLISH if direction is SignalDirection.LONG else EvidenceDirection.BEARISH
        return SignalResult(
            analysis.symbol,analysis.timestamp,direction,p,probability.no_signal,
            SignalLevels(entry_min,entry_max,stop,t1,t2,t3,rr1,rr2,rr3),
            ev,lev,
            tuple(e.reason for e in analysis.evidence if e.direction is evidence_direction and e.reason),
            (f"stop source: {levels.stop_source}","market structure may change before entry", "EV is a binary payoff proxy; fees/slippage are assumptions, funding/gaps are unmodeled", *(("target: confirmed TP1 within horizon; expired/ambiguous count as non-success",) if probability.calibrated else ("uncalibrated research score; not a measured success probability",))),
            self.version+":"+probability.model_version, probability_is_calibrated=probability.calibrated,
            research_score=probability.research_score if probability.research_score is not None else p,
            probability_model_id=probability.model_id, probability_target=probability.target,
        )
