"""unified research dataset rows
Revision ID: 0010_research_dataset
Revises: 0009_external_events
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_research_dataset"
down_revision = "0009_external_events"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "research_dataset_rows",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("dataset_version", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_price", sa.Double(), nullable=False),
        sa.Column("horizon_minutes", sa.Integer(), nullable=False),
        sa.Column("outcome_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("return_pct", sa.Double(), nullable=False),
        sa.Column("mfe_pct", sa.Double(), nullable=False),
        sa.Column("mae_pct", sa.Double(), nullable=False),
        sa.Column("features", postgresql.JSONB(), nullable=False),
        sa.Column("external_event_count", sa.Integer(), nullable=False),
        sa.Column("external_high_impact_count", sa.Integer(), nullable=False),
        sa.Column("external_weighted_sentiment", sa.Double(), nullable=True),
        sa.Column("external_max_relevance", sa.Double(), nullable=False),
        sa.Column("external_categories", postgresql.JSONB(), nullable=False),
        sa.Column("external_event_ids", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="research",
    )
    op.create_index(
        "ix_research_dataset_rows_version_time",
        "research_dataset_rows",
        ["dataset_version", "decision_time"],
        schema="research",
    )
    op.create_unique_constraint(
        "uq_research_dataset_row",
        "research_dataset_rows",
        ["dataset_version", "symbol", "decision_time", "horizon_minutes"],
        schema="research",
    )


def downgrade():
    op.drop_constraint("uq_research_dataset_row", "research_dataset_rows", schema="research")
    op.drop_index(
        "ix_research_dataset_rows_version_time",
        table_name="research_dataset_rows",
        schema="research",
    )
    op.drop_table("research_dataset_rows", schema="research")
