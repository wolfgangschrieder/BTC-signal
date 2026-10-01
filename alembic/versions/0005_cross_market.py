"""cross market observations
Revision ID: 0005_cross_market
Revises: 0004_derivatives_research + 0004_signal_outcomes
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0005_cross_market"
down_revision=("0004_derivatives_research","0004_signal_outcomes")
branch_labels=None
depends_on=None

def upgrade():
    op.create_table(
        "cross_market_observations",
        sa.Column("id",sa.BigInteger(),sa.Identity(),primary_key=True),
        sa.Column("asset",sa.String(64),nullable=False),
        sa.Column("event_time",sa.DateTime(timezone=True),nullable=False),
        sa.Column("point_in_time_available_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("value",sa.Numeric(30,12),nullable=False),
        sa.Column("source",sa.String(128),nullable=False),
        sa.Column("unit",sa.String(32),nullable=False),
        sa.Column("payload",postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        schema="intelligence",
    )
    op.create_index("ix_cross_market_asset_time","cross_market_observations",["asset","event_time"],schema="intelligence")
    op.create_index("ix_cross_market_pit","cross_market_observations",["point_in_time_available_at"],schema="intelligence")

def downgrade():
    op.drop_index("ix_cross_market_pit",table_name="cross_market_observations",schema="intelligence")
    op.drop_index("ix_cross_market_asset_time",table_name="cross_market_observations",schema="intelligence")
    op.drop_table("cross_market_observations",schema="intelligence")
