"""Phone-first authentication: nullable email, account status, verified phone uniqueness.

Revision ID: 007
Revises: 006
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("account_status", sa.String(32), nullable=False, server_default="registered"),
    )
    op.add_column(
        "users",
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.alter_column("users", "email", existing_type=sa.String(255), nullable=True)

    op.drop_index("ix_users_phone_number", table_name="users")
    op.create_index(
        "uq_users_phone_verified",
        "users",
        ["phone_number"],
        unique=True,
        postgresql_where=sa.text("phone_verified IS TRUE AND phone_number IS NOT NULL"),
    )

    op.alter_column(
        "phone_otp_sessions",
        "user_id",
        existing_type=sa.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "phone_otp_sessions",
        "user_id",
        existing_type=sa.UUID(),
        nullable=False,
    )

    op.drop_index("uq_users_phone_verified", table_name="users")
    op.create_index("ix_users_phone_number", "users", ["phone_number"], unique=False)

    op.alter_column("users", "email", existing_type=sa.String(255), nullable=False)

    op.drop_column("users", "last_active_at")
    op.drop_column("users", "account_status")
