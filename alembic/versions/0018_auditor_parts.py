"""Persist progress for complete multipart analyst delivery."""
from alembic import op

revision = '0018_auditor_parts'
down_revision = '0017_auditor_runs'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""DO $$
        DECLARE constraint_name text;
        BEGIN
            SELECT conname INTO STRICT constraint_name FROM pg_constraint
            WHERE conrelid='intelligence.auditor_runs'::regclass
              AND contype='c' AND pg_get_constraintdef(oid) LIKE '%char_length(message)%';
            EXECUTE format('ALTER TABLE intelligence.auditor_runs DROP CONSTRAINT %I', constraint_name);
        END $$""")
    op.execute("""ALTER TABLE intelligence.auditor_runs
        ADD CONSTRAINT auditor_message_size CHECK (message IS NULL OR char_length(message)<=16000),
        ADD COLUMN message_part INTEGER NOT NULL DEFAULT 0 CHECK (message_part>=0)""")


def downgrade():
    op.execute("ALTER TABLE intelligence.auditor_runs DROP COLUMN message_part")
    op.execute("ALTER TABLE intelligence.auditor_runs DROP CONSTRAINT auditor_message_size")
    # Existing full messages are retained; downgrade fails if they exceed the old bound.
    op.execute("""ALTER TABLE intelligence.auditor_runs
        ADD CHECK (message IS NULL OR char_length(message)<=3500)""")
