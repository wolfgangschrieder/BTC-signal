"""$message

Revision ID: $up_revision
Revises: $down_revision
Create Date: $create_date
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
$imports

revision: str = "$up_revision"
down_revision: Union[str, Sequence[str], None] = "$down_revision"
branch_labels = $branch_labels
depends_on = $depends_on

def upgrade() -> None:
    $upgrades

def downgrade() -> None:
    $downgrades
