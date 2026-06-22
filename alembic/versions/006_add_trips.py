"""Add trip watch sessions for family journey tracking.

Revision ID: 006
Revises: 005
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trips",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "traveler_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("destination_latitude", sa.Float(), nullable=True),
        sa.Column("destination_longitude", sa.Float(), nullable=True),
        sa.Column("destination_label", sa.String(255), nullable=True),
        sa.Column("current_latitude", sa.Float(), nullable=True),
        sa.Column("current_longitude", sa.Float(), nullable=True),
        sa.Column("accuracy_meters", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_trips_group_id", "trips", ["group_id"])
    op.create_index("ix_trips_traveler_user_id", "trips", ["traveler_user_id"])
    op.create_index("ix_trips_status", "trips", ["status"])
    op.create_index("ix_trips_traveler_status", "trips", ["traveler_user_id", "status"])
    op.create_index("ix_trips_group_status", "trips", ["group_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_trips_group_status", table_name="trips")
    op.drop_index("ix_trips_traveler_status", table_name="trips")
    op.drop_index("ix_trips_status", table_name="trips")
    op.drop_index("ix_trips_traveler_user_id", table_name="trips")
    op.drop_index("ix_trips_group_id", table_name="trips")
    op.drop_table("trips")
