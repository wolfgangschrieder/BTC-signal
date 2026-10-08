import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from research_os.data.ingestion import EventIngestionService, IngestionRejected
from research_os.data.models import EventType, RawEvent
from research_os.market.store import NormalizedMarketDataStore


@pytest.fixture
def session():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as session:
            yield session
        transaction.rollback()
    engine.dispose()


def make_event():
    now = datetime.now(UTC)
    return RawEvent(
        source="ingestion-integration",
        event_type=EventType.TRADE,
        symbol="BTCUSDT",
        event_time=now,
        ingestion_time=now,
        point_in_time_available_at=now,
        payload={"price": "100", "size": "1", "side": "Buy", "metadata": {"batch": [1, 2]}},
    )


def test_raw_normalized_and_duplicate_json_round_trip(session):
    event = make_event()
    ingestion = EventIngestionService()
    event_id, _ = ingestion.ingest(session, event)
    NormalizedMarketDataStore().persist(session, event, event_id)
    session.flush()
    payload = session.execute(
        text("SELECT payload FROM raw.events WHERE id=:id"), {"id": event_id}
    ).scalar_one()
    assert payload == event.payload
    assert (
        session.execute(
            text("SELECT count(*) FROM market.trades WHERE raw_event_id=:id"), {"id": event_id}
        ).scalar_one()
        == 1
    )
    duplicate_id, issues = ingestion.ingest(session, event)
    assert duplicate_id is None
    assert issues[-1].code.value == "duplicate"
    details = session.execute(
        text(
            "SELECT details FROM raw.quality_events WHERE source=:source ORDER BY id DESC LIMIT 1"
        ),
        {"source": event.source},
    ).scalar_one()
    assert details["fingerprint"]


def test_rejected_event_records_quality_without_raw_insert(session):
    event = make_event()
    with pytest.raises(IngestionRejected):
        EventIngestionService().ingest(
            session, event, decision_time=datetime(2020, 1, 1, tzinfo=UTC)
        )
    assert (
        session.execute(
            text("SELECT count(*) FROM raw.events WHERE source=:source"), {"source": event.source}
        ).scalar_one()
        == 0
    )
    assert (
        session.execute(
            text(
                "SELECT code FROM raw.quality_events WHERE source=:source ORDER BY id DESC LIMIT 1"
            ),
            {"source": event.source},
        ).scalar_one()
        == "pit_violation"
    )


def test_pipeline_transaction_rolls_back_raw_when_projection_fails(session, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from research_os.data import pipeline as pipeline_module

    monkeypatch.setattr(
        pipeline_module,
        "SessionLocal",
        sessionmaker(bind=session.get_bind(), join_transaction_mode="create_savepoint"),
    )
    pipeline = pipeline_module.IngestionPipeline()
    good = make_event()
    pipeline._persist_one(good)
    assert (
        session.execute(
            text("SELECT count(*) FROM raw.events WHERE source=:source"),
            {"source": good.source},
        ).scalar_one()
        == 1
    )
    bad = good.model_copy(
        update={
            "source": "ingestion-integration-rollback",
            "payload": {"price": "100", "size": "1"},
        }
    )
    with pytest.raises(KeyError, match="side"):
        pipeline._persist_one(bad)
    assert (
        session.execute(
            text("SELECT count(*) FROM raw.events WHERE source=:source"),
            {"source": bad.source},
        ).scalar_one()
        == 0
    )


def test_bybit_batch_projects_exchange_trade_ids(session):
    from research_os.exchanges.bybit.normalizer import BybitNormalizer

    item = {"s": "BTCUSDT", "p": "100", "v": "1", "S": "Buy", "T": 1767225600000}
    events = BybitNormalizer.trades(
        {"data": [{**item, "i": "audit-one"}, {**item, "i": "audit-two"}]}
    )
    ids = []
    for event in events:
        event_id, _ = EventIngestionService().ingest(session, event)
        ids.append(event_id)
        NormalizedMarketDataStore().persist(session, event, event_id)
    session.flush()
    actual = [
        session.execute(
            text("SELECT exchange_trade_id FROM market.trades WHERE raw_event_id=:id"),
            {"id": event_id},
        ).scalar_one()
        for event_id in ids
    ]
    assert actual == ["audit-one", "audit-two"]
