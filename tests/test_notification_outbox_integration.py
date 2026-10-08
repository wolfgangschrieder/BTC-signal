import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from research_os.notifications.outbox import NotificationOutboxRepository, NotificationOutboxWorker
from research_os.pipeline import live
from research_os.signals.models import SignalDirection, SignalLevels, SignalResult


class TelegramStub:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.sent = []
        self.fail = False

    async def send(self, message):
        if self.fail:
            raise RuntimeError("simulated delivery outage")
        self.sent.append(message)


@pytest.fixture
def setup(monkeypatch):
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(url)
    factory = sessionmaker(engine)
    telegram = TelegramStub("outbox-test-" + uuid4().hex)
    service = live.LiveSignalService(telegram=telegram)
    signal = SignalResult(
        "AUDIT-OUTBOX",
        datetime.now(UTC),
        SignalDirection.LONG,
        0.8,
        0.1,
        SignalLevels(100, 100, 99, 102, 103, 104, 2, 3, 4),
        1,
        1,
        (),
        (),
    )
    monkeypatch.setattr(live, "SessionLocal", factory)
    worker = NotificationOutboxWorker(telegram, session_factory=factory)
    try:
        yield factory, telegram, service, signal, worker
    finally:
        with factory.begin() as session:
            session.execute(
                text("DELETE FROM notification_outbox WHERE signal_id=:id"),
                {"id": signal.signal_id},
            )
            session.execute(
                text("DELETE FROM signal_outcomes WHERE signal_id=:id"), {"id": signal.signal_id}
            )
        engine.dispose()


def row(factory, signal):
    with factory() as session:
        return (
            session.execute(
                text("SELECT * FROM notification_outbox WHERE signal_id=:id"),
                {"id": signal.signal_id},
            )
            .mappings()
            .first()
        )


def make_due(factory, signal):
    with factory.begin() as session:
        session.execute(
            text(
                "UPDATE notification_outbox SET available_at=clock_timestamp() WHERE signal_id=:id"
            ),
            {"id": signal.signal_id},
        )


@pytest.mark.asyncio
async def test_delivery_waits_for_transaction_commit(setup):
    factory, telegram, service, signal, worker = setup
    with factory() as session:
        # Uncommitted intent is invisible to the delivery worker on another connection.
        from research_os.signals.outcomes import OutcomeStatus, SignalOutcome

        outcome = SignalOutcome(
            signal.signal_id,
            signal.symbol,
            "long",
            signal.timestamp,
            100,
            99,
            102,
            103,
            104,
            0.8,
            OutcomeStatus.PENDING,
        )
        service.outcomes.record_pending(session, outcome)
        service.outbox.enqueue(session, signal.signal_id, telegram.chat_id, "message")
        assert not await worker.deliver_once()
        assert telegram.sent == []
        session.commit()
    assert await worker.deliver_once()
    assert telegram.sent == ["message"]
    assert row(factory, signal)["sent_at"] is not None
    assert not await worker.deliver_once()


@pytest.mark.asyncio
async def test_failed_outbox_insert_rolls_back_outcome_and_prevents_delivery(setup, monkeypatch):
    factory, telegram, service, signal, worker = setup

    def fail(*args):
        raise RuntimeError("outbox insert failed")

    monkeypatch.setattr(service.outbox, "enqueue", fail)
    with pytest.raises(RuntimeError, match="outbox insert failed"):
        service._persist_emission(signal, "message")
    with factory() as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM signal_outcomes WHERE signal_id=:id"),
                {"id": signal.signal_id},
            ).scalar_one()
            == 0
        )
    assert row(factory, signal) is None
    assert not await worker.deliver_once()
    assert telegram.sent == []


@pytest.mark.asyncio
async def test_retry_and_restart_deliver_saved_message(setup):
    factory, telegram, service, signal, worker = setup
    service._persist_emission(signal, "message")
    telegram.fail = True
    assert await worker.deliver_once()
    failed = row(factory, signal)
    assert failed["sent_at"] is None
    assert failed["attempts"] == 1
    assert failed["last_error"] == "RuntimeError"
    assert failed["claim_token"] is None
    assert not await worker.deliver_once()  # Backoff has not elapsed.
    telegram.fail = False
    make_due(factory, signal)
    restarted = NotificationOutboxWorker(telegram, session_factory=factory)
    assert await restarted.deliver_once()
    assert telegram.sent == ["message"]
    assert row(factory, signal)["attempts"] == 2
    assert row(factory, signal)["last_error"] is None
    assert not await restarted.deliver_once()


def test_claim_excludes_other_workers_and_stale_acknowledgements(setup):
    factory, telegram, service, signal, _ = setup
    service._persist_emission(signal, "message")
    repository = NotificationOutboxRepository()
    with factory.begin() as first:
        claimed = repository.claim(first, telegram.chat_id)
        with factory.begin() as second:
            assert repository.claim(second, telegram.chat_id) is None
    with factory.begin() as session:
        assert repository.claim(session, telegram.chat_id) is None
        assert repository.claim(session, "different-chat") is None
    make_due(factory, signal)  # Simulate an expired lease after a crashed worker.
    with factory.begin() as session:
        reclaimed = repository.claim(session, telegram.chat_id)
        assert reclaimed["claim_token"] != claimed["claim_token"]
        assert not repository.delivered(session, claimed)
        assert repository.delivered(session, reclaimed)


def test_duplicate_emission_has_one_intent(setup):
    factory, _, service, signal, _ = setup
    service._persist_emission(signal, "original")
    service._persist_emission(signal, "replacement")
    assert row(factory, signal)["message"] == "original"
    with factory() as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM notification_outbox WHERE signal_id=:id"),
                {"id": signal.signal_id},
            ).scalar_one()
            == 1
        )


@pytest.mark.asyncio
async def test_live_writer_commits_outcome_and_message_before_delivery(setup):
    import asyncio

    factory, telegram, service, signal, worker = setup
    task = asyncio.create_task(service._cold_outcome_writer())
    try:
        service._outcome_write_queue.put_nowait((signal, "queued message"))
        await asyncio.wait_for(service._outcome_write_queue.join(), 2)
        assert telegram.sent == []
        assert row(factory, signal)["message"] == "queued message"
        assert await worker.deliver_once()
        assert telegram.sent == ["queued message"]
    finally:
        await service._outcome_write_queue.put(service._writer_stop)
        await task


@pytest.mark.asyncio
async def test_crash_after_send_reclaims_intent_without_losing_message(setup, monkeypatch):
    factory, telegram, service, signal, worker = setup
    service._persist_emission(signal, "message")

    def fail_ack(*args):
        raise RuntimeError("simulated acknowledgement outage")

    monkeypatch.setattr(worker.repository, "delivered", fail_ack)
    with pytest.raises(RuntimeError, match="acknowledgement outage"):
        await worker.deliver_once()
    assert telegram.sent == ["message"]
    assert row(factory, signal)["sent_at"] is None
    assert row(factory, signal)["claim_token"] is not None
    make_due(factory, signal)
    restarted = NotificationOutboxWorker(telegram, session_factory=factory)
    assert await restarted.deliver_once()
    # At-least-once delivery can repeat the accepted message after a lost ACK.
    assert telegram.sent == ["message", "message"]
    assert row(factory, signal)["sent_at"] is not None


@pytest.mark.asyncio
async def test_health_recovers_only_when_no_pending_delivery_remains(setup):
    factory, telegram, service, signal, _ = setup
    health = []
    worker = NotificationOutboxWorker(telegram, session_factory=factory, on_health=health.append)
    assert not await worker.deliver_once()
    assert health[-1] is True
    service._persist_emission(signal, "message")
    telegram.fail = True
    assert await worker.deliver_once()
    assert health[-1] is False
    assert not await worker.deliver_once()
    assert health[-1] is False
    telegram.fail = False
    make_due(factory, signal)
    assert await worker.deliver_once()
    assert health[-1] is True
