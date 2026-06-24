"""Emergency intelligence: skills, group emergency types, responder profile, alert recipients.

Revision ID: 008
Revises: 007
"""

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


SKILL_SEED = [
    ("first_aid", "First Aid", "medical", 10),
    ("cpr", "CPR Certified", "medical", 20),
    ("nurse", "Nurse", "medical", 30),
    ("doctor", "Doctor", "medical", 40),
    ("mental_health", "Mental Health Support", "medical", 50),
    ("mechanic", "Mechanic", "automotive", 60),
    ("roadside_assistance", "Roadside Assistance", "automotive", 70),
    ("security", "Security", "safety", 80),
    ("local_contact", "Local Contact", "support", 90),
    ("emergency_contact", "Emergency Contact", "support", 100),
    ("other", "Other", "support", 110),
]


def upgrade() -> None:
    # --- User responder-profile columns ---
    op.add_column("users", sa.Column("location_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("certifications", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("users", sa.Column("languages", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("users", sa.Column("vehicle_available", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("medical_background", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("available_for_emergencies", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "users",
        sa.Column("location_visibility", sa.String(32), nullable=False, server_default="groups"),
    )

    # --- Group policy columns ---
    op.add_column("groups", sa.Column("priority", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("groups", sa.Column("visibility", sa.String(32), nullable=False, server_default="private"))

    # --- AlertResponse distance ---
    op.add_column("alert_responses", sa.Column("distance_km", sa.Float(), nullable=True))

    # --- skills catalog ---
    op.create_table(
        "skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("category", sa.String(64), nullable=False, server_default="other"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_skills_code", "skills", ["code"], unique=True)

    # --- user_skills ---
    op.create_table(
        "user_skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.String(32), nullable=False, server_default="basic"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "skill_id", name="uq_user_skill"),
    )
    op.create_index("ix_user_skills_user_id", "user_skills", ["user_id"])
    op.create_index("ix_user_skills_skill_id", "user_skills", ["skill_id"])

    # --- group_emergency_types ---
    op.create_table(
        "group_emergency_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("group_id", "alert_type", name="uq_group_emergency_type"),
    )
    op.create_index("ix_group_emergency_types_group_id", "group_emergency_types", ["group_id"])

    # --- alert_recipients ---
    op.create_table(
        "alert_recipients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("notified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("alert_id", "user_id", name="uq_alert_recipient"),
    )
    op.create_index("ix_alert_recipients_alert_id", "alert_recipients", ["alert_id"])
    op.create_index("ix_alert_recipients_user_id", "alert_recipients", ["user_id"])

    # --- seed skills ---
    skills_table = sa.table(
        "skills",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        skills_table,
        [
            {"id": uuid.uuid4(), "code": code, "name": name, "category": cat, "sort_order": order}
            for code, name, cat, order in SKILL_SEED
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_alert_recipients_user_id", table_name="alert_recipients")
    op.drop_index("ix_alert_recipients_alert_id", table_name="alert_recipients")
    op.drop_table("alert_recipients")

    op.drop_index("ix_group_emergency_types_group_id", table_name="group_emergency_types")
    op.drop_table("group_emergency_types")

    op.drop_index("ix_user_skills_skill_id", table_name="user_skills")
    op.drop_index("ix_user_skills_user_id", table_name="user_skills")
    op.drop_table("user_skills")

    op.drop_index("ix_skills_code", table_name="skills")
    op.drop_table("skills")

    op.drop_column("alert_responses", "distance_km")

    op.drop_column("groups", "visibility")
    op.drop_column("groups", "priority")

    op.drop_column("users", "location_visibility")
    op.drop_column("users", "available_for_emergencies")
    op.drop_column("users", "medical_background")
    op.drop_column("users", "vehicle_available")
    op.drop_column("users", "languages")
    op.drop_column("users", "certifications")
    op.drop_column("users", "location_updated_at")
