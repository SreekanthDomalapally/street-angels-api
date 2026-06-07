from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.repositories.user_repository import UserRepository
from app.schemas import UserLookupMatch, UserLookupRequest, UserLookupResponse, UserResponse, UserUpdateRequest

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_profile(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user


@router.post("/lookup", response_model=UserLookupResponse)
async def lookup_users(
    body: UserLookupRequest,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserLookupResponse:
    """Return which contact emails already have a YouHoo Alert account."""
    users = await UserRepository(db).list_by_emails([str(email) for email in body.emails])
    return UserLookupResponse(
        matches=[
            UserLookupMatch(email=user.email, user_id=user.id, full_name=user.full_name)
            for user in users
        ]
    )


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    body: UserUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    if body.phone_number is not None:
        user.phone_number = body.phone_number
    if body.profile_photo is not None:
        user.profile_photo = body.profile_photo
    if body.notification_preferences is not None:
        user.notification_preferences = body.notification_preferences
    if body.last_known_latitude is not None:
        user.last_known_latitude = body.last_known_latitude
    if body.last_known_longitude is not None:
        user.last_known_longitude = body.last_known_longitude
    return await UserRepository(db).update(user)
