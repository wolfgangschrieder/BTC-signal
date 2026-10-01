"""external event evidence

Revision ID: 0009_external_events
Revises: 0008_execution_audit
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_external_events"
down_revision = "0008_execution_audit"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS intelligence")
    op.create_table(
        "external_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("event_id", sa.String(256), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source", sa.String(256), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("point_in_time_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("impact", sa.String(16), nullable=False),
        sa.Column("relevance", sa.Float(), nullable=False),
        sa.Column("sentiment", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("event_id", "source", name="uq_external_events_event_source"),
        schema="intelligence",
    )
    op.create_index(
        "ix_external_events_event_time",
        "external_events",
        ["event_time"],
        schema="intelligence",
    )
    op.create_index(
        "ix_external_events_pit",
        "external_events",
        ["point_in_time_available_at"],
        schema="intelligence",
    )


def downgrade():
    op.drop_index("ix_external_events_pit", table_name="external_events", schema="intelligence")
    op.drop_index("ix_external_events_event_time", table_name="external_events", schema="intelligence")
    op.drop_table("external_events", schema="intelligence")
