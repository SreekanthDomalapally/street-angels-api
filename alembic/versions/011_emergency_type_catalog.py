"""Refresh emergency type catalog labels and retire need_pickup / general_help."""

import uuid

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE emergency_types SET name = 'Medical', sort_order = 10 WHERE code = 'medical'")
    op.execute(
        "UPDATE emergency_types SET name = 'Safety', sort_order = 20 WHERE code = 'personal_safety'"
    )
    op.execute(
        "UPDATE emergency_types SET name = 'Breakdown', sort_order = 30 WHERE code = 'car_breakdown'"
    )
    op.execute(
        "UPDATE emergency_types SET name = 'Pickup', sort_order = 40 WHERE code = 'need_pickup'"
    )
    op.execute(
        "UPDATE emergency_types SET name = 'Lost', sort_order = 50 WHERE code = 'lost_or_stranded'"
    )
    op.execute("UPDATE emergency_types SET name = 'Custom', sort_order = 60 WHERE code = 'custom'")

    # Remove general_help from groups and alerts; drop from catalog.
    op.execute(
        """
        DELETE FROM group_emergency_types
        WHERE alert_type = 'general_help'
        """
    )
    op.execute(
        """
        UPDATE alerts
        SET alert_type = 'need_pickup'
        WHERE alert_type = 'general_help'
        """
    )
    op.execute("DELETE FROM emergency_types WHERE code = 'general_help'")


def downgrade() -> None:
    op.execute(
        f"""
        INSERT INTO emergency_types (id, code, name, severity, sort_order)
        VALUES ('{uuid.uuid4()}', 'general_help', 'General Help', 4, 60)
        ON CONFLICT (code) DO NOTHING
        """
    )
