"""Add optional blood group to user profile."""

import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("blood_group", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "blood_group")
