"""cross market dataset registry
Revision ID: 0007_cross_market_dataset
Revises: 0006_cross_market_outcomes
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0007_cross_market_dataset"
down_revision="0006_cross_market_outcomes"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table(
        "cross_market_datasets",
        sa.Column("dataset_version",sa.String(128),primary_key=True),
        sa.Column("symbol",sa.String(32),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("min_samples",sa.Integer(),nullable=False),
        sa.Column("window_size",sa.Integer(),nullable=False),
        sa.Column("horizons_minutes",postgresql.JSONB(),nullable=False),
        sa.Column("decision_start",sa.DateTime(timezone=True),nullable=True),
        sa.Column("decision_end",sa.DateTime(timezone=True),nullable=True),
        sa.Column("row_count",sa.Integer(),nullable=False),
        sa.Column("skipped_count",sa.Integer(),nullable=False),
        sa.Column("notes",sa.Text(),nullable=True),
        schema="research",
    )

def downgrade():
    op.drop_table("cross_market_datasets",schema="research")
