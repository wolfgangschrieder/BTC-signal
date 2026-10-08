"""Index bounded high-frequency retention scans.
Revision ID: 0013_retention_index
Revises: 0012_notification_outbox
"""
from alembic import op

revision = '0013_retention_index'
down_revision = '0012_notification_outbox'
branch_labels = None
depends_on = None


def upgrade():
    # Concurrent build avoids blocking ingestion on an existing populated VPS.
    with op.get_context().autocommit_block():
        op.execute("""CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_raw_events_retention
            ON raw.events (ingestion_time, id)
            WHERE source='bybit' AND event_type IN
                ('trade','ticker','orderbook_update','orderbook_snapshot')""")


def downgrade():
    op.execute('DROP INDEX IF EXISTS raw.ix_raw_events_retention')
