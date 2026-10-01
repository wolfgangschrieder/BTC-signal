from datetime import datetime, timezone
from research_os.research.cross_market_repository import CrossMarketOutcomeRepository

class FakeResult:
    def mappings(self): return self
    def all(self): return []
class FakeSession:
    def execute(self,statement,params):
        self.statement=str(statement); self.params=params
        return FakeResult()

def test_outcome_repository_uses_deterministic_key():
    session=FakeSession()
    class Outcome:
        asset="VIX"
        state_timestamp=datetime(2026,1,1,tzinfo=timezone.utc)
        outcome_timestamp=datetime(2026,1,1,1,tzinfo=timezone.utc)
        horizon_minutes=60
        normalized_value=2.0
        btc_return_pct=.01
        btc_mfe_pct=.02
        btc_mae_pct=-.01
    CrossMarketOutcomeRepository().save(session,Outcome())
    assert "ON CONFLICT" in session.statement
    assert session.params["asset"]=="VIX"
    assert session.params["horizon"]==60
