"""Add firebase identity, phone verification, trusted contacts, phone invites.

Revision ID: 005
Revises: 004
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("firebase_uid", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("phone_verified", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("country_code", sa.String(8), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_users_firebase_uid", "users", ["firebase_uid"], unique=True)
    op.create_index("ix_users_phone_number", "users", ["phone_number"], unique=False)

    op.execute("UPDATE users SET firebase_uid = google_sub WHERE google_sub IS NOT NULL")

    op.create_table(
        "trusted_contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="accepted"),
        sa.Column("source", sa.String(32), nullable=False, server_default="contacts"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("owner_user_id", "contact_user_id", name="uq_trusted_contact_pair"),
    )
    op.create_index("ix_trusted_contacts_owner_user_id", "trusted_contacts", ["owner_user_id"])
    op.create_index("ix_trusted_contacts_contact_user_id", "trusted_contacts", ["contact_user_id"])

    op.create_table(
        "phone_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("inviter_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invited_phone_number", sa.String(32), nullable=False),
        sa.Column("invited_email", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("invite_code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("invite_code", name="uq_phone_invite_code"),
    )
    op.create_index("ix_phone_invites_invited_phone_number", "phone_invites", ["invited_phone_number"])
    op.create_index("ix_phone_invites_invite_code", "phone_invites", ["invite_code"])

    op.create_table(
        "phone_otp_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phone_number", sa.String(32), nullable=False),
        sa.Column("otp_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_phone_otp_sessions_user_id", "phone_otp_sessions", ["user_id"])

    op.add_column("group_invites", sa.Column("invitee_phone", sa.String(32), nullable=True))
    op.create_index("ix_group_invites_invitee_phone", "group_invites", ["invitee_phone"])


def downgrade() -> None:
    op.drop_index("ix_group_invites_invitee_phone", table_name="group_invites")
    op.drop_column("group_invites", "invitee_phone")
    op.drop_table("phone_otp_sessions")
    op.drop_table("phone_invites")
    op.drop_table("trusted_contacts")
    op.drop_index("ix_users_phone_number", table_name="users")
    op.drop_index("ix_users_firebase_uid", table_name="users")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "country_code")
    op.drop_column("users", "phone_verified")
    op.drop_column("users", "firebase_uid")
