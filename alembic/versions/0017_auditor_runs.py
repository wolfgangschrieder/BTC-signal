"""Bounded analyst journal with atomic API budget reservation and delivery lease."""
from alembic import op

revision = '0017_auditor_runs'
down_revision = '0016_derivative_retention'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE intelligence.auditor_runs (
        run_id UUID PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('tick','daily')),
        period_start TIMESTAMPTZ NOT NULL, period_end TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        status TEXT NOT NULL CHECK (status IN ('started','completed','failed')),
        model TEXT NOT NULL, tokens INTEGER NOT NULL CHECK (tokens>=0),
        snapshot JSONB NOT NULL, report JSONB, message TEXT, error_type VARCHAR(96),
        sent_at TIMESTAMPTZ, available_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        delivery_until TIMESTAMPTZ NOT NULL, claim_token UUID,
        attempts INTEGER NOT NULL DEFAULT 0, delivery_error VARCHAR(96),
        UNIQUE(kind,period_start), CHECK (period_start<period_end),
        CHECK (octet_length(snapshot::text)<=32000),
        CHECK (report IS NULL OR octet_length(report::text)<=24000),
        CHECK (message IS NULL OR char_length(message)<=3500)
    )''')
    op.execute('CREATE INDEX ix_auditor_created ON intelligence.auditor_runs (created_at)')
    op.execute("CREATE INDEX ix_auditor_delivery ON intelligence.auditor_runs (available_at) WHERE status='completed' AND sent_at IS NULL")

    op.execute("""CREATE VIEW intelligence.auditor_findings AS
        SELECT run_id,kind,period_end,status,report->>'verdict' AS verdict,
               item.ordinality AS finding_number,item.finding
        FROM intelligence.auditor_runs
        CROSS JOIN LATERAL jsonb_array_elements(coalesce(report->'findings','[]'::jsonb))
            WITH ORDINALITY AS item(finding,ordinality)
        WHERE status='completed'
    """)


def downgrade():
    op.execute('DROP VIEW intelligence.auditor_findings')
    op.execute('DROP TABLE intelligence.auditor_runs')
