"""Preserve failed reports and their API reservations during bounded recovery."""
from alembic import op

revision = '0020_auditor_attempts'
down_revision = '0019_auditor_tasks'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE intelligence.auditor_runs ADD COLUMN attempt_number INTEGER NOT NULL DEFAULT 1 CHECK (attempt_number BETWEEN 1 AND 2)')
    op.execute('ALTER TABLE intelligence.auditor_runs DROP CONSTRAINT auditor_runs_kind_period_start_key')
    op.execute('ALTER TABLE intelligence.auditor_runs ADD CONSTRAINT auditor_runs_window_attempt_key UNIQUE(kind,period_start,attempt_number)')


def downgrade():
    # Refuse to erase paid attempt history merely to restore the old uniqueness rule.
    op.execute('ALTER TABLE intelligence.auditor_runs ADD CONSTRAINT auditor_runs_kind_period_start_key UNIQUE(kind,period_start)')
    op.execute('ALTER TABLE intelligence.auditor_runs DROP CONSTRAINT auditor_runs_window_attempt_key')
    op.execute('ALTER TABLE intelligence.auditor_runs DROP COLUMN attempt_number')
