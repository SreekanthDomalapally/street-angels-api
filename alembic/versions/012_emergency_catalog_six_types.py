"""Restore original six-type catalog: drop general_help, short one-word labels."""

import uuid

from alembic import op

revision = "012"
down_revision = "011"
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

    # Re-insert need_pickup if migration 011 removed it.
    op.execute(
        f"""
        INSERT INTO emergency_types (id, code, name, severity, sort_order)
        VALUES ('{uuid.uuid4()}', 'need_pickup', 'Pickup', 3, 40)
        ON CONFLICT (code) DO UPDATE
        SET name = EXCLUDED.name, severity = EXCLUDED.severity, sort_order = EXCLUDED.sort_order
        """
    )

    # Retired types -> need_pickup (merge group rows safely).
    for retired in ("general_help", "my_neighbourhood"):
        op.execute(
            f"""
            INSERT INTO group_emergency_types (id, group_id, alert_type)
            SELECT gen_random_uuid(), retired.group_id, 'need_pickup'
            FROM group_emergency_types retired
            WHERE retired.alert_type = '{retired}'
            GROUP BY retired.group_id
            HAVING NOT EXISTS (
                SELECT 1
                FROM group_emergency_types existing
                WHERE existing.group_id = retired.group_id
                  AND existing.alert_type = 'need_pickup'
            )
            """
        )
        op.execute(
            f"""
            DELETE FROM group_emergency_types
            WHERE alert_type = '{retired}'
            """
        )
        op.execute(
            f"""
            UPDATE alerts
            SET alert_type = 'need_pickup'
            WHERE alert_type = '{retired}'
            """
        )
        op.execute(f"DELETE FROM emergency_types WHERE code = '{retired}'")


def downgrade() -> None:
    op.execute(
        f"""
        INSERT INTO emergency_types (id, code, name, severity, sort_order)
        VALUES ('{uuid.uuid4()}', 'general_help', 'General Help', 4, 60)
        ON CONFLICT (code) DO NOTHING
        """
    )
