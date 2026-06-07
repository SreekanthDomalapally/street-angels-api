from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    ContactDirectoryResponse,
    ContactGroupsUpdateRequest,
    ContactInviteGroupsRequest,
)
from app.services.contact_service import ContactService

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("/directory", response_model=ContactDirectoryResponse)
async def get_contact_directory(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ContactDirectoryResponse:
    return await ContactService(db).directory(user)


@router.put("/{user_id}/groups", status_code=status.HTTP_204_NO_CONTENT)
async def set_contact_groups(
    user_id: UUID,
    body: ContactGroupsUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await ContactService(db).set_member_groups(user, user_id, body)


@router.post("/invites/groups", status_code=status.HTTP_204_NO_CONTENT)
async def assign_invite_groups(
    body: ContactInviteGroupsRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await ContactService(db).assign_invite_groups(user, body.email, list(body.group_ids))
