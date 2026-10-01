"""foundation schemas"""
from alembic import op
import sqlalchemy as sa

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    for schema in ("raw", "world", "signals", "research", "system"):
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(32)),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingestion_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("point_in_time_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="raw",
    )
    op.create_index("ix_raw_events_symbol_event_time", "events", ["symbol", "event_time"], schema="raw")
    op.create_table(
        "market_state_vectors",
        sa.Column("state_id", sa.String(128), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("point_in_time_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vector_version", sa.String(32), nullable=False),
        sa.Column("feature_version", sa.String(64), nullable=False),
        sa.Column("factor_version", sa.String(64), nullable=False),
        sa.Column("regime_version", sa.String(64), nullable=False),
        sa.Column("code_version", sa.String(128), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.Column("market_state", sa.String(32), nullable=False),
        sa.Column("data_quality", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        schema="world",
    )
    op.create_index("ix_world_msv_symbol_timestamp", "market_state_vectors", ["symbol", "timestamp"], schema="world")

def downgrade() -> None:
    op.drop_index("ix_world_msv_symbol_timestamp", table_name="market_state_vectors", schema="world")
    op.drop_table("market_state_vectors", schema="world")
    op.drop_index("ix_raw_events_symbol_event_time", table_name="events", schema="raw")
    op.drop_table("events", schema="raw")
    for schema in ("system", "research", "signals", "world", "raw"):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
