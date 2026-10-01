"""persistent execution audit and human interaction state

Revision ID: 0008_execution_audit
Revises: 0007_cross_market_dataset
"""
from alembic import op
import sqlalchemy as sa

revision="0008_execution_audit"
down_revision="0007_cross_market_dataset"
branch_labels=None
depends_on=None

def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS execution")

    op.create_table(
        "orders",
        sa.Column("client_order_id",sa.String(128),primary_key=True),
        sa.Column("signal_id",sa.String(128),nullable=False),
        sa.Column("symbol",sa.String(32),nullable=False),
        sa.Column("side",sa.String(8),nullable=False),
        sa.Column("order_type",sa.String(16),nullable=False),
        sa.Column("quantity",sa.Numeric(38,18),nullable=False),
        sa.Column("limit_price",sa.Numeric(38,18),nullable=True),
        sa.Column("stop_loss",sa.Numeric(38,18),nullable=False),
        sa.Column("take_profit",sa.Numeric(38,18),nullable=False),
        sa.Column("status",sa.String(32),nullable=False),
        sa.Column("exchange_order_id",sa.String(128),nullable=True),
        sa.Column("reason",sa.Text(),nullable=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        schema="execution",
    )
    op.create_index("ix_execution_orders_signal_id","orders",["signal_id"],schema="execution")

    op.create_table(
        "events",
        sa.Column("id",sa.BigInteger(),sa.Identity(),primary_key=True),
        sa.Column("client_order_id",sa.String(128),nullable=False),
        sa.Column("signal_id",sa.String(128),nullable=False),
        sa.Column("event_type",sa.String(64),nullable=False),
        sa.Column("from_status",sa.String(32),nullable=True),
        sa.Column("to_status",sa.String(32),nullable=False),
        sa.Column("reason",sa.Text(),nullable=True),
        sa.Column("exchange_order_id",sa.String(128),nullable=True),
        sa.Column("event_time",sa.DateTime(timezone=True),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        schema="execution",
    )
    op.create_index("ix_execution_events_order_time","events",["client_order_id","event_time"],schema="execution")

    op.create_table(
        "confirmations",
        sa.Column("signal_id",sa.String(128),primary_key=True),
        sa.Column("status",sa.String(32),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("confirmed_at",sa.DateTime(timezone=True),nullable=True),
        sa.Column("cancelled_at",sa.DateTime(timezone=True),nullable=True),
        schema="execution",
    )

def downgrade():
    op.drop_table("confirmations",schema="execution")
    op.drop_index("ix_execution_events_order_time",table_name="events",schema="execution")
    op.drop_table("events",schema="execution")
    op.drop_index("ix_execution_orders_signal_id",table_name="orders",schema="execution")
    op.drop_table("orders",schema="execution")
    op.execute("DROP SCHEMA IF EXISTS execution")
