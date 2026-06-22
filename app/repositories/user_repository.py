from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def list_by_emails(self, emails: list[str]) -> list[User]:
        normalized = sorted({email.strip().lower() for email in emails if email.strip()})
        if not normalized:
            return []
        result = await self.db.execute(select(User).where(User.email.in_(normalized)))
        return list(result.scalars().all())

    async def get_by_google_sub(self, google_sub: str) -> User | None:
        result = await self.db.execute(select(User).where(User.google_sub == google_sub))
        return result.scalar_one_or_none()

    async def get_by_firebase_uid(self, firebase_uid: str) -> User | None:
        result = await self.db.execute(select(User).where(User.firebase_uid == firebase_uid))
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone_e164: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.phone_number == phone_e164, User.phone_verified.is_(True))
        )
        return result.scalar_one_or_none()

    async def list_by_phones(self, phones: list[str]) -> list[User]:
        normalized = sorted({phone.strip() for phone in phones if phone.strip()})
        if not normalized:
            return []
        result = await self.db.execute(
            select(User).where(
                User.phone_number.in_(normalized),
                User.phone_verified.is_(True),
            )
        )
        return list(result.scalars().all())

    async def create(self, user: User) -> User:
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update(self, user: User) -> User:
        await self.db.flush()
        await self.db.refresh(user)
        return user
