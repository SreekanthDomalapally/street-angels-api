"""Canonical responder-skill catalog. Seeds the ``skills`` table."""

from __future__ import annotations


class SkillMeta:
    __slots__ = ("code", "name", "category", "sort_order")

    def __init__(self, code: str, name: str, category: str, sort_order: int) -> None:
        self.code = code
        self.name = name
        self.category = category
        self.sort_order = sort_order


SKILLS: list[SkillMeta] = [
    SkillMeta("first_aid", "First Aid", "medical", 10),
    SkillMeta("cpr", "CPR Certified", "medical", 20),
    SkillMeta("nurse", "Nurse", "medical", 30),
    SkillMeta("doctor", "Doctor", "medical", 40),
    SkillMeta("mental_health", "Mental Health Support", "medical", 50),
    SkillMeta("mechanic", "Mechanic", "automotive", 60),
    SkillMeta("roadside_assistance", "Roadside Assistance", "automotive", 70),
    SkillMeta("security", "Security", "safety", 80),
    SkillMeta("local_contact", "Local Contact", "support", 90),
    SkillMeta("emergency_contact", "Emergency Contact", "support", 100),
    SkillMeta("other", "Other", "support", 110),
]

SKILL_LEVELS = ("basic", "intermediate", "professional")

# Which skills are most relevant to each emergency type — drives responder ranking.
EMERGENCY_TYPE_SKILLS: dict[str, list[str]] = {
    "medical": ["doctor", "nurse", "cpr", "first_aid", "mental_health"],
    "personal_safety": ["security", "emergency_contact", "local_contact"],
    "car_breakdown": ["mechanic", "roadside_assistance"],
    "lost_or_stranded": ["local_contact", "emergency_contact"],
    "my_neighbourhood": ["local_contact", "emergency_contact"],
    "custom": [],
}

_BY_CODE = {s.code: s for s in SKILLS}


def is_valid_skill(code: str) -> bool:
    return code in _BY_CODE


def relevant_skills(alert_type: str) -> list[str]:
    from app.common.emergency_types import canonical_code

    return EMERGENCY_TYPE_SKILLS.get(canonical_code(alert_type), [])
