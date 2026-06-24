"""Performance indexes for hot SOS and admin group queries."""

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_alerts_creator_active
        ON alerts (created_by)
        WHERE status = 'active'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_group_members_user_role
        ON group_members (user_id, role)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_group_members_user_role")
    op.execute("DROP INDEX IF EXISTS ix_alerts_creator_active")
