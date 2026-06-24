"""Platform hardening: notification outbox, delivery audit, emergency_types catalog, indexes.

Revision ID: 009
Revises: 008
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

EMERGENCY_TYPE_SEED = [
    ("medical", "Medical Help", 1, 10),
    ("personal_safety", "Personal Safety", 1, 20),
    ("car_breakdown", "Car Breakdown", 3, 30),
    ("need_pickup", "Need Pickup", 3, 40),
    ("lost_or_stranded", "Lost or Stranded", 2, 50),
    ("general_help", "General Help", 4, 60),
    ("custom", "Custom", 3, 70),
]


def upgrade() -> None:
    # --- emergency_types catalog (Phase 4) ---
    op.create_table(
        "emergency_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_emergency_types_code", "emergency_types", ["code"], unique=True)

    emergency_types = sa.table(
        "emergency_types",
        sa.column("id", postgresql.UUID),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("severity", sa.Integer),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        emergency_types,
        [
            {
                "id": uuid.uuid4(),
                "code": code,
                "name": name,
                "severity": severity,
                "sort_order": sort_order,
            }
            for code, name, severity, sort_order in EMERGENCY_TYPE_SEED
        ],
    )

    # --- transactional notification outbox (Phase 1) ---
    op.create_table(
        "notification_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notification_outbox_status", "notification_outbox", ["status", "created_at"])

    # --- delivery audit on recipients (Phase 1) ---
    op.add_column(
        "alert_recipients",
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "alert_recipients",
        sa.Column("delivery_status", sa.String(32), nullable=False, server_default="pending"),
    )
    op.add_column(
        "alert_recipients",
        sa.Column("delivery_error", sa.Text(), nullable=True),
    )

    # --- alert severity snapshot ---
    op.add_column("alerts", sa.Column("severity", sa.Integer(), nullable=True))

    # --- indexes (Phase 4) ---
    op.create_index("ix_phone_otp_sessions_phone", "phone_otp_sessions", ["phone_number"])
    op.create_index("ix_group_invites_status_created", "group_invites", ["status", "created_at"])
    op.create_index(
        "ix_alert_location_user_time",
        "alert_location_updates",
        ["alert_id", "user_id", "recorded_at"],
    )

    # Global unique device token (Phase 4)
    op.create_index("ix_device_tokens_token_unique", "device_tokens", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_device_tokens_token_unique", table_name="device_tokens")
    op.drop_index("ix_alert_location_user_time", table_name="alert_location_updates")
    op.drop_index("ix_group_invites_status_created", table_name="group_invites")
    op.drop_index("ix_phone_otp_sessions_phone", table_name="phone_otp_sessions")
    op.drop_column("alerts", "severity")
    op.drop_column("alert_recipients", "delivery_error")
    op.drop_column("alert_recipients", "delivery_status")
    op.drop_column("alert_recipients", "notified_at")
    op.drop_index("ix_notification_outbox_status", table_name="notification_outbox")
    op.drop_table("notification_outbox")
    op.drop_index("ix_emergency_types_code", table_name="emergency_types")
    op.drop_table("emergency_types")
