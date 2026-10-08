"""Versioned calibration artifacts and forecast provenance; historical rows stay NULL."""

from alembic import op

revision = "0015_calibration_models"
down_revision = "0014_outcome_execution_policy"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE signal_outcomes ADD COLUMN research_score DOUBLE PRECISION CHECK (research_score BETWEEN 0 AND 1)"
    )
    op.execute("ALTER TABLE signal_outcomes ADD COLUMN probability_model_id TEXT")
    op.execute("ALTER TABLE signal_outcomes ADD COLUMN calibration_context TEXT")
    op.execute("""CREATE TABLE intelligence.calibration_models (
        model_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, direction TEXT NOT NULL,
        context_id TEXT NOT NULL, artifact JSONB NOT NULL, accepted BOOLEAN NOT NULL,
        created_at TIMESTAMPTZ NOT NULL, CHECK (direction IN ('long','short'))
    )""")


def downgrade():
    op.execute("DROP TABLE intelligence.calibration_models")
    op.execute(
        "ALTER TABLE signal_outcomes DROP COLUMN calibration_context, DROP COLUMN probability_model_id, DROP COLUMN research_score"
    )
