"""derivatives research outcomes
Revision ID: 0004_derivatives_research
Revises: 0003_timeseries
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="0004_derivatives_research"
down_revision="0003_timeseries"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table(
        "derivatives_state_outcomes",
        sa.Column("id",sa.BigInteger(),sa.Identity(),primary_key=True),
        sa.Column("symbol",sa.String(32),nullable=False),
        sa.Column("state_timestamp",sa.DateTime(timezone=True),nullable=False),
        sa.Column("decision_time",sa.DateTime(timezone=True),nullable=False),
        sa.Column("state_version",sa.String(64),nullable=False),
        sa.Column("state",postgresql.JSONB(),nullable=False),
        sa.Column("state_fingerprint",sa.String(128),nullable=False),
        sa.Column("outcome_timestamp",sa.DateTime(timezone=True),nullable=False),
        sa.Column("horizon_minutes",sa.Integer(),nullable=False),
        sa.Column("return_pct",sa.Numeric(20,10)),
        sa.Column("mfe_pct",sa.Numeric(20,10)),
        sa.Column("mae_pct",sa.Numeric(20,10)),
        sa.Column("volatility",sa.Numeric(20,10)),
        sa.Column("oi_change_after",sa.Numeric(20,10)),
        sa.Column("regime_after",sa.String(64)),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.UniqueConstraint("symbol","state_timestamp","horizon_minutes","state_version",name="uq_derivatives_state_outcome"),
    )
    op.create_index("ix_derivatives_state_outcomes_symbol_time","derivatives_state_outcomes",["symbol","state_timestamp"],schema="research")
    op.create_index("ix_derivatives_state_outcomes_fingerprint","derivatives_state_outcomes",["state_fingerprint"],schema="research")

def downgrade():
    op.drop_index("ix_derivatives_state_outcomes_fingerprint",table_name="derivatives_state_outcomes",schema="research")
    op.drop_index("ix_derivatives_state_outcomes_symbol_time",table_name="derivatives_state_outcomes",schema="research")
    op.drop_table("derivatives_state_outcomes",schema="research")
