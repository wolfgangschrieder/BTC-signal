from datetime import datetime, timedelta, timezone
from research_os.cross_market.models import CrossMarketObservation
from research_os.cross_market.research import CrossMarketResearchEngine

def test_research_snapshot_uses_only_pit_valid_history():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    obs=[CrossMarketObservation("VIX",t+timedelta(days=i),t+timedelta(days=i),100+i,"test") for i in range(21)]
    late=CrossMarketObservation("VIX",t+timedelta(days=20),t+timedelta(days=30),999,"late")
    result=CrossMarketResearchEngine().build(t+timedelta(days=20),obs+[late],as_of=t+timedelta(days=20),min_samples=5)
    assert result.observations["VIX"].value==120
    assert result.normalized["VIX"].available
