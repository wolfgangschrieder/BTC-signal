"""Versioned research brief from the inspected repository, not live process telemetry."""
from research_os.intelligence.analyzer import MarketAnalyzer
from research_os.intelligence.probability import ProbabilityEngine

CONTEXT_VERSION = 'research-brief-v2'


def project_evidence():
    return {
        'project.context_version': CONTEXT_VERSION,
        'project.instrument': 'Bybit BTCUSDT linear perpetual; human execution, no autotrading. Spot short-borrow is not the assumed instrument; funding may apply.',
        'project.code_versions': {'analysis':MarketAnalyzer.version,'score':ProbabilityEngine.version,
                                 'scope':'Installed auditor code; not verification of market-app version or in-memory history'},
        'project.feature_groups': {
            'technical_direction':['return_1','return_5','tf_15m_return_1','tf_1h_return_1','tf_4h_return_1','tf_1d_return_1'],
            'microstructure_direction':['orderbook_imbalance','orderflow_imbalance','orderflow_price_delta_divergence'],
            'risk_or_neutral':['atr_14','realized_vol','orderflow_absorption','derivatives_price_oi_divergence','derivatives_liquidation_imbalance','derivatives_oi_change'],
            'limitations':'These groups describe analysis-v3. Neutral evidence is not a directional vote. ATR/risk and mandatory data-quality prerequisites must remain identical across proposed variants.'},
        'project.live_execution': 'Saved policy/costs govern each forecast. conservative-midpoint-v2 models entry at entry-zone midpoint, 60-minute default horizon; entry+exit or SL+TP touched in one OHLC bar is ambiguous. No actual fill, portfolio or human delay replay.',
        'project.available_research': 'threshold_check: current-model rescoring, chronological train/holdout, next-candle-open market entry, ATR stop 1x / TP1 1.5x, 30-minute horizon, independent overlapping candidates. Existing implementation does not run feature-group ablation.',
        'project.cost_scenarios': {'label':'Experimental assumptions, NOT account tariffs or observed fills',
                                 'fee_bps_per_side':[5.5], 'slippage_bps_per_side':[0,2,5],
                                 'limitations':'Funding, spread and manual-entry delay need explicit assumptions or measurements. Avoid double-counting spread embedded in slippage. Do not change live settings.'},
        'project.experiment_protocol': 'Design TA-only, microstructure-only, combined using identical PIT rows, prerequisites, risk levels and costs. Freeze chronological train/validation/test; purge horizons crossing boundaries; select parameters without test. Report net expectation, drawdown, sample size, ambiguity and cost sensitivity; overlapping candidates are not independent portfolio trades. Profit hypotheses may be specified before outcomes; evaluation requires data.',
    }
