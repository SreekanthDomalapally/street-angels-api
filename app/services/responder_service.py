from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.skills import SKILL_LEVELS
from app.core.exceptions import ValidationError
from app.models import Skill, UserSkill
from app.schemas import UserSkillInput, UserSkillItem


class ResponderService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_skills(self, user_id: UUID) -> list[UserSkillItem]:
        result = await self.db.execute(
            select(UserSkill, Skill)
            .join(Skill, Skill.id == UserSkill.skill_id)
            .where(UserSkill.user_id == user_id)
            .order_by(Skill.sort_order)
        )
        return [
            UserSkillItem(
                skill_code=skill.code,
                name=skill.name,
                category=skill.category,
                level=us.level,
                verified=us.verified,
            )
            for us, skill in result.all()
        ]

    async def set_skills(
        self, user_id: UUID, inputs: list[UserSkillInput]
    ) -> list[UserSkillItem]:
        # Dedup by code (last one wins) so we never violate the unique constraint.
        by_code: dict[str, UserSkillInput] = {i.skill_code: i for i in inputs}
        codes = list(by_code.keys())

        skill_rows: dict[str, Skill] = {}
        if codes:
            result = await self.db.execute(select(Skill).where(Skill.code.in_(codes)))
            skill_rows = {s.code: s for s in result.scalars().all()}

        unknown = [c for c in codes if c not in skill_rows]
        if unknown:
            raise ValidationError(f"Unknown skill(s): {', '.join(unknown)}")

        await self.db.execute(delete(UserSkill).where(UserSkill.user_id == user_id))
        for code, item in by_code.items():
            level = item.level if item.level in SKILL_LEVELS else "basic"
            self.db.add(
                UserSkill(user_id=user_id, skill_id=skill_rows[code].id, level=level)
            )
        await self.db.flush()
        return await self.list_skills(user_id)
