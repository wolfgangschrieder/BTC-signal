from datetime import datetime, timezone
from research_os.research.liquidity_attribution import LiquidityRiskObservation, summarize, compare_sources

def _row(source, ret):
    return LiquidityRiskObservation(
        datetime(2026,1,1,tzinfo=timezone.utc),"long",100.0,2.0,98.0,source,
        98.0 if source=="liquidity" else None,500.0 if source=="liquidity" else None,
        0.99 if source=="liquidity" else None,source=="liquidity",
        3000 if source=="liquidity" else 0,60,ret,0.03,-0.01)

def test_liquidity_attribution_is_descriptive():
    summary=summarize([_row("liquidity",.01),_row("liquidity",-.005)],"liquidity",60)
    assert summary.sample_size==2
    assert summary.positive_rate==0.5
    assert summary.stop_distance_atr==1.0

def test_compare_sources_keeps_categories_separate():
    result=compare_sources([_row("liquidity",.01),_row("atr",.002)],60)
    assert result["liquidity"].sample_size==1
    assert result["atr"].sample_size==1
    assert result["atr_fallback"].sample_size==0

def test_from_signal_outcome_preserves_risk_source():
    from research_os.research.liquidity_attribution import from_signal_outcome
    row=from_signal_outcome(
        {"signal_time":datetime(2026,1,1,tzinfo=timezone.utc),"direction":"long",
         "entry_price":100,"stop_loss":98,"realized_return":0.01,"mfe":0.03,"mae":-0.01,
         "horizon_minutes":60},
        "liquidity",98.0,500.0,0.99,True,3000,2.0)
    assert row.stop_source=="liquidity"
    assert row.cluster_persistent is True
    assert row.realized_return_pct==0.01
