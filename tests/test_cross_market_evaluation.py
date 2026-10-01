from datetime import datetime, timedelta, timezone
from research_os.research.cross_market_dataset import CrossMarketDatasetRow
from research_os.research.cross_market_evaluation import evaluate, evaluate_threshold

def row(t,asset,horizon,z,ret):
    return CrossMarketDatasetRow(t,asset,horizon,1.0,z,0.8,True,20,ret,0.02,-0.01)

def test_evaluation_filters_asset_and_horizon():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    rows=[row(t,"VIX",60,2,.02),row(t+timedelta(days=1),"VIX",60,-2,-.01),
          row(t,"VIX",240,2,.50),row(t,"SPX",60,2,.30)]
    result=evaluate(rows,"VIX",60)
    assert result.sample_size==2
    assert result.positive_rate==.5

def test_threshold_evaluation_is_descriptive():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    rows=[row(t,"VIX",60,3,.02),row(t+timedelta(days=1),"VIX",60,-1,-.01)]
    result=evaluate_threshold(rows,"VIX",60,lower=2)
    assert result.sample_size==1
    assert result.mean_return==.02
