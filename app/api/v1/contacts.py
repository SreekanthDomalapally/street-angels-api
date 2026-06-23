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
    ContactMatchRequest,
    ContactMatchResponse,
    TrustedContactAddRequest,
)
from app.services.contact_service import ContactService
from app.services.identity_service import IdentityService

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.post("/match", response_model=ContactMatchResponse)
async def match_contacts(
    body: ContactMatchRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ContactMatchResponse:
    region = body.country_code or "IE"
    payload = [{"phone": c.phone, "display_name": c.display_name} for c in body.contacts]
    result = await IdentityService(db).match_contacts(user, payload, region)
    return ContactMatchResponse(**result)


@router.post("/add", status_code=status.HTTP_204_NO_CONTENT)
async def add_trusted_contact(
    body: TrustedContactAddRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await IdentityService(db).add_trusted_contact(user, body.contact_user_id, body.display_name)


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
    await ContactService(db).assign_invite_groups(
        user,
        list(body.group_ids),
        email=str(body.email) if body.email else None,
        phone_number=body.phone_number,
        country_code=body.country_code,
    )
