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
        "UPDATE emergency_types SET name = 'Car Breakdown', sort_order = 30 WHERE code = 'car_breakdown'"
    )
    op.execute(
        "UPDATE emergency_types SET name = 'I am Lost!', sort_order = 40 WHERE code = 'lost_or_stranded'"
    )
    op.execute("UPDATE emergency_types SET name = 'Custom', sort_order = 60 WHERE code = 'custom'")

    op.execute(
        f"""
        INSERT INTO emergency_types (id, code, name, severity, sort_order)
        VALUES ('{uuid.uuid4()}', 'my_neighbourhood', 'My neighbourhood', 3, 50)
        ON CONFLICT (code) DO UPDATE
        SET name = EXCLUDED.name, severity = EXCLUDED.severity, sort_order = EXCLUDED.sort_order
        """
    )

    for table in ("group_emergency_types", "alerts"):
        op.execute(
            f"""
            UPDATE {table}
            SET alert_type = 'my_neighbourhood'
            WHERE alert_type IN ('need_pickup', 'general_help')
            """
        )

    op.execute("DELETE FROM emergency_types WHERE code IN ('need_pickup', 'general_help')")


def downgrade() -> None:
    op.execute(
        f"""
        INSERT INTO emergency_types (id, code, name, severity, sort_order)
        VALUES
            ('{uuid.uuid4()}', 'need_pickup', 'Need Pickup', 3, 40),
            ('{uuid.uuid4()}', 'general_help', 'General Help', 4, 60)
        ON CONFLICT (code) DO NOTHING
        """
    )

    op.execute("DELETE FROM emergency_types WHERE code = 'my_neighbourhood'")

    op.execute("UPDATE emergency_types SET name = 'Medical Help' WHERE code = 'medical'")
    op.execute("UPDATE emergency_types SET name = 'Personal Safety' WHERE code = 'personal_safety'")
    op.execute("UPDATE emergency_types SET name = 'Lost or Stranded' WHERE code = 'lost_or_stranded'")
