"""signal outcomes and reporting
Revision ID: 0004_signal_outcomes_branch
Revises: 0003_timeseries
"""
from alembic import op
import sqlalchemy as sa
revision="0004_signal_outcomes_branch"; down_revision="0003_timeseries"; branch_labels=None; depends_on=None
def upgrade():
    op.create_table("signal_outcomes",
        sa.Column("id",sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column("signal_id",sa.String(128),nullable=False,unique=True),
        sa.Column("symbol",sa.String(32),nullable=False),
        sa.Column("direction",sa.String(16),nullable=False),
        sa.Column("signal_time",sa.DateTime(timezone=True),nullable=False),
        sa.Column("entry_price",sa.Numeric(38,18),nullable=False),
        sa.Column("stop_loss",sa.Numeric(38,18),nullable=False),
        sa.Column("tp1",sa.Numeric(38,18),nullable=False),
        sa.Column("tp2",sa.Numeric(38,18),nullable=False),
        sa.Column("tp3",sa.Numeric(38,18),nullable=False),
        sa.Column("probability",sa.Numeric(10,8),nullable=False),
        sa.Column("status",sa.String(16),nullable=False),
        sa.Column("realized_return",sa.Numeric(20,10)),
        sa.Column("mfe",sa.Numeric(20,10)),
        sa.Column("mae",sa.Numeric(20,10)),
        sa.Column("resolved_at",sa.DateTime(timezone=True)),
        sa.Column("horizon_minutes",sa.Integer()),
        sa.Column("reason",sa.Text()),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
    )
    op.create_index("ix_signal_outcomes_symbol_time","signal_outcomes",["symbol","signal_time"])
    op.create_index("ix_signal_outcomes_status_time","signal_outcomes",["status","resolved_at"])
def downgrade():
    op.drop_table("signal_outcomes")
