from datetime import datetime, timezone

from research_os.research.research_dataset import (
    ResearchDataset,
    ResearchDatasetRepository,
    ResearchDatasetRow,
)


class FakeResult:
    def scalar_one(self):
        return 1


class FakeSession:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return FakeResult()


def sample():
    row = ResearchDatasetRow(
        symbol="BTCUSDT",
        decision_time=datetime(2026, 1, 2, 12, tzinfo=timezone.utc),
        entry_price=100.0,
        horizon_minutes=60,
        outcome_time=datetime(2026, 1, 2, 13, tzinfo=timezone.utc),
        return_pct=0.01,
        mfe_pct=0.02,
        mae_pct=-0.01,
        features=(("atr", 1.2),),
        external_event_count=1,
        external_high_impact_count=1,
        external_weighted_sentiment=0.5,
        external_max_relevance=0.9,
        external_categories=("macro",),
        external_event_ids=("evt-1",),
    )
    return ResearchDataset("BTCUSDT", "research-dataset-v1:60:3600:0", (row,), 0)


def test_save_is_idempotent_and_persists_pit_fields():
    session = FakeSession()
    dataset = sample()
    assert ResearchDatasetRepository().save(session, dataset) == 1
    sql, params = session.calls[0]
    assert "ON CONFLICT" in sql
    assert "outcome_time" in sql
    assert "decision_time" in sql
    assert params["decision_time"] == dataset.rows[0].decision_time
    assert params["outcome_time"] == dataset.rows[0].outcome_time


def test_repository_exposes_dataset_pit_audit():
    session = FakeSession()
    assert ResearchDatasetRepository().assert_pit_safe(session, "v1", "BTCUSDT") == 1
    sql, params = session.calls[0]
    assert "outcome_time <= decision_time" in sql
    assert params == {"version": "v1", "symbol": "BTCUSDT"}
