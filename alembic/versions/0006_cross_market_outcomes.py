"""cross market research outcomes
Revision ID: 0006_cross_market_outcomes
Revises: 0005_cross_market
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="0006_cross_market_outcomes"
down_revision="0005_cross_market"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table(
        "cross_market_outcomes",
        sa.Column("id",sa.BigInteger(),sa.Identity(),primary_key=True),
        sa.Column("symbol",sa.String(32),nullable=False),
        sa.Column("asset",sa.String(64),nullable=False),
        sa.Column("state_timestamp",sa.DateTime(timezone=True),nullable=False),
        sa.Column("outcome_timestamp",sa.DateTime(timezone=True),nullable=False),
        sa.Column("horizon_minutes",sa.Integer(),nullable=False),
        sa.Column("normalized_value",sa.Double(),nullable=True),
        sa.Column("btc_return_pct",sa.Double(),nullable=False),
        sa.Column("btc_mfe_pct",sa.Double(),nullable=False),
        sa.Column("btc_mae_pct",sa.Double(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        schema="research",
    )
    op.create_index("ix_cross_market_outcomes_asset_time","cross_market_outcomes",["asset","state_timestamp"],schema="research")
    op.create_index("ix_cross_market_outcomes_symbol_time","cross_market_outcomes",["symbol","state_timestamp"],schema="research")
    op.create_unique_constraint(
        "uq_cross_market_outcome",
        "cross_market_outcomes",
        ["symbol","asset","state_timestamp","horizon_minutes"],
        schema="research",
    )

def downgrade():
    op.drop_constraint("uq_cross_market_outcome","cross_market_outcomes",schema="research")
    op.drop_index("ix_cross_market_outcomes_symbol_time",table_name="cross_market_outcomes",schema="research")
    op.drop_index("ix_cross_market_outcomes_asset_time",table_name="cross_market_outcomes",schema="research")
    op.drop_table("cross_market_outcomes",schema="research")
