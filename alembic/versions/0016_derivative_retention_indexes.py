"""Index ticker-derived rows for bounded raw-event retention batches."""
from alembic import op

revision = '0016_derivative_retention'
down_revision = '0015_calibration_models'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('funding_rates', 'open_interest'):
        op.execute(f'CREATE INDEX ix_{table}_retention_raw_event ON derivatives.{table} (raw_event_id)')


def downgrade():
    for table in ('funding_rates', 'open_interest'):
        op.execute(f'DROP INDEX derivatives.ix_{table}_retention_raw_event')
