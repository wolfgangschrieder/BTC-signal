from datetime import datetime, timezone

from research_os.research.research_dataset import ResearchDataset, ResearchDatasetRow
from research_os.research.research_dataset_repository import ResearchDatasetRepository


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
        "BTCUSDT",
        datetime(2026, 1, 2, 12, tzinfo=timezone.utc),
        100.0,
        60,
        datetime(2026, 1, 2, 13, tzinfo=timezone.utc),
        0.01, 0.02, -0.01,
        (("atr", 1.2),),
        (("DOLLAR_BROAD", 1.0, 0.5, 0.8, 30, True),),
        1, 1, 0.5, 0.9, ("macro",), ("evt-1",),
    )
    return ResearchDataset("BTCUSDT", "research-dataset-v2:60:3600:0", (row,), 0)


def test_save_persists_pit_and_cross_market_fields():
    session = FakeSession()
    dataset = sample()
    assert ResearchDatasetRepository().save(session, dataset) == 1
    sql, params = session.calls[0]
    assert "ON CONFLICT" in sql
    assert "cross_market" in sql
    assert params["decision_time"] == dataset.rows[0].decision_time
    assert params["outcome_time"] == dataset.rows[0].outcome_time


def test_repository_exposes_dataset_pit_audit():
    session = FakeSession()
    assert ResearchDatasetRepository().assert_pit_safe(session, "v1", "BTCUSDT") == 1
    sql, params = session.calls[0]
    assert "outcome_time <= decision_time" in sql
    assert params == {"version": "v1", "symbol": "BTCUSDT"}
