import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from research_os.research.research_dataset import (
    EvidenceProvenance,
    ResearchDataset,
    ResearchDatasetRow,
)
from research_os.research.research_dataset_repository import ResearchDatasetRepository


@pytest.fixture
def db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(url)
    with engine.begin() as connection:
        yield connection
        connection.execute(
            text(
                "DELETE FROM research.research_dataset_rows "
                "WHERE dataset_version=:version AND symbol=:symbol"
            ),
            {"version": "integration-v1", "symbol": "BTCUSDT"},
        )
    engine.dispose()


def make_dataset():
    t = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
    provenance = (
        EvidenceProvenance(
            "external_event",
            "evt-1",
            t - timedelta(minutes=1),
            t - timedelta(minutes=1),
            t - timedelta(seconds=30),
            1,
        ),
    )
    row = ResearchDatasetRow(
        "BTCUSDT", t, 100.0, 60, t + timedelta(hours=1),
        0.01, 0.02, -0.01,
        (("atr", 1.2),),
        (("DOLLAR_BROAD", 1.0, 0.5, 0.8, 30, True),),
        1, 1, 0.5, 0.9, ("macro",), ("evt-1",),
        provenance,
    )
    return ResearchDataset("BTCUSDT", "integration-v1", (row,), 0)


def test_repository_round_trip_and_pit_audit(db):
    repo = ResearchDatasetRepository()
    dataset = make_dataset()

    assert repo.save(db, dataset) == 1
    assert repo.count(db, dataset.version, dataset.symbol) == 1
    assert repo.assert_pit_safe(db, dataset.version, dataset.symbol) == 0

    stored = db.execute(
        text(
            "SELECT decision_time, outcome_time, features, cross_market, "
            "external_event_ids, provenance "
            "FROM research.research_dataset_rows "
            "WHERE dataset_version=:version AND symbol=:symbol"
        ),
        {"version": dataset.version, "symbol": dataset.symbol},
    ).mappings().one()

    assert stored["decision_time"] == dataset.rows[0].decision_time
    assert stored["outcome_time"] == dataset.rows[0].outcome_time
    assert stored["features"]["atr"] == 1.2
    assert stored["cross_market"][0][0] == "DOLLAR_BROAD"
    assert stored["external_event_ids"] == ["evt-1"]
    assert stored["provenance"][0]["source"] == "external_event"
    assert stored["provenance"][0]["source_id"] == "evt-1"
    assert stored["provenance"][0]["item_count"] == 1
    assert stored["provenance"][0]["available_at"] == (t := dataset.rows[0].decision_time - timedelta(seconds=30)).isoformat()


def test_repository_upsert_replaces_existing_row(db):
    repo = ResearchDatasetRepository()
    dataset = make_dataset()
    assert repo.save(db, dataset) == 1

    row = dataset.rows[0]
    updated = ResearchDataset(
        dataset.symbol,
        dataset.version,
        (ResearchDatasetRow(
            row.symbol, row.decision_time, 101.0, row.horizon_minutes,
            row.outcome_time, 0.02, row.mfe_pct, row.mae_pct,
            row.features, row.cross_market, row.external_event_count,
            row.external_high_impact_count, row.external_weighted_sentiment,
            row.external_max_relevance, row.external_categories,
            row.external_event_ids, row.provenance,
        ),),
        0,
    )
    assert repo.save(db, updated) == 1
    stored = db.execute(
        text(
            "SELECT entry_price, return_pct "
            "FROM research.research_dataset_rows "
            "WHERE dataset_version=:version AND symbol=:symbol"
        ),
        {"version": dataset.version, "symbol": dataset.symbol},
    ).mappings().one()
    assert stored["entry_price"] == 101.0
    assert stored["return_pct"] == 0.02
