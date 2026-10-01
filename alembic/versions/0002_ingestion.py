"""ingestion quality and deduplication

Revision ID: 0002_ingestion
Revises: 0001_foundation
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_ingestion"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.alter_column(
        "events",
        "payload",
        schema="raw",
        type_=postgresql.JSONB,
        existing_type=sa.JSON(),
        postgresql_using="payload::jsonb",
    )
    op.create_table(
        "event_fingerprints",
        sa.Column("fingerprint", sa.String(64), primary_key=True),
        sa.Column("event_id", sa.BigInteger(), sa.ForeignKey("raw.events.id"), nullable=False, unique=True),
        schema="raw",
    )
    op.create_table(
        "quality_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True)),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="raw",
    )
    op.create_index(
        "ix_raw_quality_events_source_event_time",
        "quality_events",
        ["source", "event_time"],
        schema="raw",
    )


def downgrade() -> None:
    op.drop_index("ix_raw_quality_events_source_event_time", table_name="quality_events", schema="raw")
    op.drop_table("quality_events", schema="raw")
    op.drop_table("event_fingerprints", schema="raw")
