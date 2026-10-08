"""Durable signal notification outbox.

Revision ID: 0012_notification_outbox
Revises: 0011_research_dataset_provenance
"""

import sqlalchemy as sa

from alembic import op

revision = "0012_notification_outbox"
down_revision = "0011_research_dataset_provenance"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "signal_id", sa.String(128), sa.ForeignKey("signal_outcomes.signal_id"), nullable=False
        ),
        sa.Column("chat_id", sa.String(128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claim_token", sa.String(36)),
        sa.Column("last_error", sa.String(128)),
        sa.UniqueConstraint("signal_id", "chat_id", name="uq_notification_outbox_signal_chat"),
    )
    op.create_index(
        "ix_notification_outbox_pending",
        "notification_outbox",
        ["chat_id", "available_at"],
        postgresql_where=sa.text("sent_at IS NULL"),
    )


def downgrade():
    op.drop_table("notification_outbox")
