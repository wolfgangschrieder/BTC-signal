"""Persist per-signal execution assumptions without rewriting historical results."""
from alembic import op

revision = "0014_outcome_execution_policy"
down_revision = "0013_retention_index"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE signal_outcomes ADD COLUMN fee_bps DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (fee_bps >= 0)")
    op.execute("ALTER TABLE signal_outcomes ADD COLUMN slippage_bps DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (slippage_bps >= 0)")
    op.execute("ALTER TABLE signal_outcomes ADD COLUMN execution_policy TEXT NOT NULL DEFAULT 'legacy-entry-only'")


def downgrade():
    op.execute("ALTER TABLE signal_outcomes DROP COLUMN execution_policy, DROP COLUMN slippage_bps, DROP COLUMN fee_bps")
