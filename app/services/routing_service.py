"""Smart SOS routing: pick and rank the right responders for an alert.

Flow: SOS type -> matching groups -> members (deduped) -> ranked recipients.
Groups with no configured emergency types match everything (backward compatible).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.emergency_types import canonical_code
from app.common.geo import haversine_km
from app.common.skills import relevant_skills
from app.models import Alert, AlertRecipient, Skill, User, UserSkill
from app.repositories.group_repository import GroupRepository

# Scoring weights (sum = 1.0).
_W_SKILL = 0.40
_W_PROXIMITY = 0.30
_W_AVAILABILITY = 0.15
_W_GROUP = 0.15
# Beyond this distance proximity score floors out.
_MAX_USEFUL_KM = 50.0


@dataclass
class Candidate:
    user: User
    group_id: UUID
    group_priority: int
    distance_km: float | None = None
    score: float = 0.0
    skill_codes: set[str] = field(default_factory=set)


class RoutingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.groups = GroupRepository(db)

    async def build_recipients(self, creator: User, alert: Alert) -> list[AlertRecipient]:
        memberships = await self.groups.list_memberships_for_user(creator.id)
        all_group_ids = [m.group_id for m in memberships]
        type_map = await self.groups.list_emergency_types_for_groups(all_group_ids)

        priority_by_group: dict[UUID, int] = {}
        matching_group_ids: list[UUID] = []
        for m in memberships:
            configured = type_map.get(m.group_id, [])
            alert_code = canonical_code(alert.alert_type)
            configured_codes = {canonical_code(code) for code in configured}
            if not configured or alert_code in configured_codes:
                matching_group_ids.append(m.group_id)
                priority_by_group[m.group_id] = m.group.priority if m.group else 3

        # Fallback: always honor the group the user explicitly chose.
        if alert.group_id not in matching_group_ids:
            matching_group_ids.append(alert.group_id)
            priority_by_group.setdefault(alert.group_id, 3)

        members = await self.groups.list_members_for_groups(matching_group_ids)

        # Dedup by user, keeping the highest-priority group (lowest number).
        best: dict[UUID, Candidate] = {}
        for member in members:
            if member.user_id == creator.id or member.user is None:
                continue
            group_priority = priority_by_group.get(member.group_id, 3)
            current = best.get(member.user_id)
            if current is None or group_priority < current.group_priority:
                best[member.user_id] = Candidate(
                    user=member.user,
                    group_id=member.group_id,
                    group_priority=group_priority,
                )

        if not best:
            return []

        await self._attach_skills(best)
        self._score(best, creator, alert)

        ranked = sorted(best.values(), key=lambda c: c.score, reverse=True)
        from app.core.config import settings

        cap = settings.recipient_cap
        if cap > 0:
            ranked = ranked[:cap]
        recipients: list[AlertRecipient] = []
        for rank, cand in enumerate(ranked, start=1):
            recipients.append(
                AlertRecipient(
                    alert_id=alert.id,
                    user_id=cand.user.id,
                    group_id=cand.group_id,
                    distance_km=cand.distance_km,
                    rank=rank,
                    score=round(cand.score, 4),
                    notified=True,
                )
            )
        return recipients

    async def _attach_skills(self, candidates: dict[UUID, Candidate]) -> None:
        user_ids = list(candidates.keys())
        result = await self.db.execute(
            select(UserSkill.user_id, Skill.code)
            .join(Skill, Skill.id == UserSkill.skill_id)
            .where(UserSkill.user_id.in_(user_ids))
        )
        for user_id, code in result.all():
            candidates[user_id].skill_codes.add(code)

    def _score(self, candidates: dict[UUID, Candidate], creator: User, alert: Alert) -> None:
        wanted = set(relevant_skills(alert.alert_type))
        has_origin = creator.last_known_latitude is not None and creator.last_known_longitude is not None

        for cand in candidates.values():
            # Skill match
            if not wanted:
                skill_score = 0.5
            elif cand.skill_codes:
                skill_score = len(cand.skill_codes & wanted) / len(wanted)
            else:
                skill_score = 0.0

            # Proximity
            user = cand.user
            if (
                has_origin
                and user.last_known_latitude is not None
                and user.last_known_longitude is not None
            ):
                cand.distance_km = round(
                    haversine_km(
                        float(creator.last_known_latitude),
                        float(creator.last_known_longitude),
                        float(user.last_known_latitude),
                        float(user.last_known_longitude),
                    ),
                    2,
                )
                proximity_score = max(0.0, 1.0 - cand.distance_km / _MAX_USEFUL_KM)
            else:
                proximity_score = 0.3  # unknown distance -> neutral-low

            availability_score = 1.0 if user.available_for_emergencies else 0.2
            group_score = (6 - cand.group_priority) / 5  # priority 1 -> 1.0, 5 -> 0.2

            cand.score = (
                _W_SKILL * skill_score
                + _W_PROXIMITY * proximity_score
                + _W_AVAILABILITY * availability_score
                + _W_GROUP * group_score
            )
