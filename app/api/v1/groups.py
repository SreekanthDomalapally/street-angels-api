from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    GroupCreateRequest,
    GroupDetailResponse,
    GroupInviteListItemResponse,
    GroupInviteRequest,
    GroupInviteResponse,
    GroupListItemResponse,
    GroupMemberAddRequest,
    GroupResponse,
)
from app.services.group_service import GroupService

router = APIRouter(prefix="/groups", tags=["groups"])


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GroupResponse:
    return await GroupService(db).create(user, body)


@router.get("", response_model=list[GroupListItemResponse])
async def list_groups(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[GroupListItemResponse]:
    return await GroupService(db).list_for_user(user.id)


@router.get("/invites/mine", response_model=list[GroupInviteListItemResponse])
async def list_my_group_invites(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[GroupInviteListItemResponse]:
    return await GroupService(db).list_my_pending_invites(user)


@router.post("/invites/{invite_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
async def accept_group_invite(
    invite_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await GroupService(db).accept_invite(user, invite_id)


@router.post("/invites/{invite_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline_group_invite(
    invite_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await GroupService(db).decline_invite(user, invite_id)


@router.get("/{group_id}", response_model=GroupDetailResponse)
async def get_group(
    group_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GroupDetailResponse:
    return await GroupService(db).get_detail(user, group_id)


@router.post("/{group_id}/members", status_code=204)
async def add_member(
    group_id: UUID,
    body: GroupMemberAddRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await GroupService(db).add_member(user, group_id, body)


@router.delete("/{group_id}/members/{user_id}", status_code=204)
async def remove_member(
    group_id: UUID,
    user_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await GroupService(db).remove_member(user, group_id, user_id)


@router.post("/{group_id}/invites", response_model=GroupInviteResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    group_id: UUID,
    body: GroupInviteRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GroupInviteResponse:
    invite = await GroupService(db).invite(user, group_id, body)
    return GroupInviteResponse.model_validate(invite)
