"""Bounded analyst tasks and local operational alerts."""
from alembic import op

revision = '0019_auditor_tasks'
down_revision = '0018_auditor_parts'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE intelligence.auditor_runs ADD COLUMN delivery_message TEXT CHECK (delivery_message IS NULL OR char_length(delivery_message)<=3500)")
    op.execute("ALTER TABLE intelligence.auditor_runs DROP CONSTRAINT auditor_runs_kind_check")
    op.execute("ALTER TABLE intelligence.auditor_runs ADD CONSTRAINT auditor_runs_kind_check CHECK (kind IN ('tick','periodic','daily','alert'))")
    op.execute("""CREATE TABLE intelligence.auditor_tasks (
        task_id UUID PRIMARY KEY, dedup_key VARCHAR(160) NOT NULL UNIQUE,
        kind TEXT NOT NULL CHECK (kind IN ('data_quality','signal_review','experiment','hypothesis','costs')),
        priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 3),
        status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting','running','completed','insufficient_data','failed')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        context JSONB NOT NULL CHECK (octet_length(context::text)<=8000),
        run_id UUID, result JSONB CHECK (result IS NULL OR octet_length(result::text)<=8000)
    )""")
    op.execute("CREATE INDEX ix_auditor_tasks_pending ON intelligence.auditor_tasks (priority,created_at) WHERE status='waiting'")


def downgrade():
    op.execute('DROP TABLE intelligence.auditor_tasks')
    op.execute('ALTER TABLE intelligence.auditor_runs DROP COLUMN delivery_message')
    op.execute("DELETE FROM intelligence.auditor_runs WHERE kind='alert'")
    op.execute("ALTER TABLE intelligence.auditor_runs DROP CONSTRAINT auditor_runs_kind_check")
    op.execute("ALTER TABLE intelligence.auditor_runs ADD CONSTRAINT auditor_runs_kind_check CHECK (kind IN ('tick','daily'))")
