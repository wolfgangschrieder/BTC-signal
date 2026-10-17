"""Separate directional forecasts from hypothetical execution outcomes."""
from alembic import op

revision = "0021_signal_forecasts"
down_revision = "0020_auditor_attempts"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE signal_forecasts (
        signal_id VARCHAR(128) NOT NULL REFERENCES signal_outcomes(signal_id) ON DELETE CASCADE,
        horizon_minutes INTEGER NOT NULL CHECK (horizon_minutes > 0),
        status TEXT NOT NULL DEFAULT 'pending',
        reference_price DOUBLE PRECISION,
        reference_time TIMESTAMPTZ,
        reference_source TEXT,
        endpoint_time TIMESTAMPTZ,
        directional_return DOUBLE PRECISION,
        mfe DOUBLE PRECISION,
        mae DOUBLE PRECISION,
        evaluated_at TIMESTAMPTZ,
        reason TEXT,
        PRIMARY KEY (signal_id, horizon_minutes))""")
    op.execute("CREATE INDEX ix_signal_forecasts_pending ON signal_forecasts(status)")
    op.execute("ALTER TABLE signal_outcomes ADD COLUMN execution_state TEXT, ADD COLUMN horizon_return DOUBLE PRECISION")


def downgrade():
    op.execute("ALTER TABLE signal_outcomes DROP COLUMN execution_state, DROP COLUMN horizon_return")
    op.execute("DROP TABLE signal_forecasts")
