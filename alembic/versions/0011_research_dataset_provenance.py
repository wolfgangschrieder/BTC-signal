"""research dataset evidence provenance

Revision ID: 0011_research_dataset_provenance
Revises: 0010_research_dataset
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_research_dataset_provenance"
down_revision = "0010_research_dataset"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "research_dataset_rows",
        sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        schema="research",
    )
    op.alter_column(
        "research_dataset_rows",
        "provenance",
        server_default=None,
        schema="research",
    )


def downgrade():
    op.drop_column("research_dataset_rows", "provenance", schema="research")
