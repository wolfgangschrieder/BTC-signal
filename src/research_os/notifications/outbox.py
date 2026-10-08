"""Transactional intent storage and leased, at-least-once Telegram delivery."""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from sqlalchemy import text

from research_os.database.session import SessionLocal

logger = logging.getLogger(__name__)


class NotificationOutboxRepository:
    def enqueue(self, session, signal_id: str, chat_id: str, message: str) -> None:
        session.execute(
            text("""
            INSERT INTO notification_outbox (signal_id, chat_id, message)
            VALUES (:signal_id, :chat_id, :message)
            ON CONFLICT (signal_id, chat_id) DO NOTHING
        """),
            {"signal_id": signal_id, "chat_id": chat_id, "message": message},
        )

    def claim(self, session, chat_id: str, lease_seconds: int = 60):
        return (
            session.execute(
                text("""
            WITH candidate AS (
                SELECT id FROM notification_outbox
                WHERE chat_id=:chat_id AND sent_at IS NULL
                  AND available_at <= clock_timestamp()
                ORDER BY available_at, id
                FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE notification_outbox AS item
            SET claim_token=:token, attempts=attempts+1,
                available_at=clock_timestamp()+make_interval(secs => :lease)
            FROM candidate WHERE item.id=candidate.id
            RETURNING item.id, item.message, item.claim_token, item.attempts
        """),
                {"chat_id": chat_id, "token": str(uuid4()), "lease": lease_seconds},
            )
            .mappings()
            .first()
        )

    def pending_exists(self, session, chat_id: str) -> bool:
        return bool(
            session.execute(
                text("""
            SELECT EXISTS (SELECT 1 FROM notification_outbox
                           WHERE chat_id=:chat_id AND sent_at IS NULL)
        """),
                {"chat_id": chat_id},
            ).scalar_one()
        )

    def delivered(self, session, item) -> bool:
        return (
            session.execute(
                text("""
            UPDATE notification_outbox
            SET sent_at=clock_timestamp(), claim_token=NULL, last_error=NULL
            WHERE id=:id AND claim_token=:token AND sent_at IS NULL
        """),
                {"id": item["id"], "token": item["claim_token"]},
            ).rowcount
            == 1
        )

    def retry(self, session, item, error: Exception) -> None:
        delay = min(300, 2 ** min(item["attempts"], 9))
        session.execute(
            text("""
            UPDATE notification_outbox
            SET claim_token=NULL, last_error=:error,
                available_at=clock_timestamp()+make_interval(secs => :delay)
            WHERE id=:id AND claim_token=:token AND sent_at IS NULL
        """),
            {
                "id": item["id"],
                "token": item["claim_token"],
                "error": type(error).__name__,
                "delay": delay,
            },
        )


class NotificationOutboxWorker:
    def __init__(self, telegram, *, session_factory=None, on_health=None):
        self.telegram = telegram
        self.session_factory = session_factory or SessionLocal
        self.repository = NotificationOutboxRepository()
        self.on_health = on_health or (lambda healthy: None)

    def _transaction(self, method, *args):
        with self.session_factory() as session:
            result = method(session, *args)
            session.commit()
            return result

    async def deliver_once(self) -> bool:
        item = await asyncio.to_thread(
            self._transaction, self.repository.claim, self.telegram.chat_id
        )
        if item is None:
            pending = await asyncio.to_thread(
                self._transaction, self.repository.pending_exists, self.telegram.chat_id
            )
            # A recovered database with no backlog must unblock new signal emission.
            self.on_health(not pending)
            return False
        try:
            # Bound delivery below the 60s claim lease; no DB transaction spans HTTP.
            await asyncio.wait_for(self.telegram.send(item["message"]), timeout=20)
        except Exception as error:  # noqa: BLE001 - every delivery failure must preserve the intent
            self.on_health(False)
            await asyncio.to_thread(self._transaction, self.repository.retry, item, error)
        else:
            acknowledged = await asyncio.to_thread(
                self._transaction, self.repository.delivered, item
            )
            self.on_health(acknowledged)
        return True

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                if await self.deliver_once():
                    continue
            except Exception:  # noqa: BLE001 - retry DB/adapter failures without exposing credentials
                # Avoid logging HTTP exception strings that may contain bot tokens.
                self.on_health(False)
                logger.error("Notification outbox operation failed; retrying")
            try:
                await asyncio.wait_for(stop.wait(), timeout=1)
            except TimeoutError:
                pass
