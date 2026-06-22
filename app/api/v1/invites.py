from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models import User
from app.schemas import PhoneInviteCreateRequest, PhoneInviteDetailResponse, PhoneInviteResponse
from app.services.identity_service import IdentityService

router = APIRouter(prefix="/invites", tags=["invites"])

INVITE_BASE_URL = "https://youhooalert.com/invite"


@router.post("", response_model=PhoneInviteResponse)
@limiter.limit("20/minute")
async def create_invite(
    request: Request,
    body: PhoneInviteCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhoneInviteResponse:
    invite = await IdentityService(db).create_phone_invite(
        user,
        body.phone_number,
        body.display_name,
        body.group_id,
        body.country_code,
    )
    return PhoneInviteResponse(
        id=invite.id,
        invite_code=invite.invite_code,
        invite_url=f"{INVITE_BASE_URL}/{invite.invite_code}",
        invited_phone_last4=invite.invited_phone_number[-4:],
        status=invite.status,
        expires_at=invite.expires_at,
    )


@router.get("/{invite_code}", response_model=PhoneInviteDetailResponse)
async def get_invite(
    invite_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhoneInviteDetailResponse:
    invite = await IdentityService(db).get_invite_by_code(invite_code)
    inviter = await IdentityService(db).users.get_by_id(invite.inviter_user_id)
    return PhoneInviteDetailResponse(
        invite_code=invite.invite_code,
        inviter_name=inviter.full_name if inviter else "Someone",
        display_name=invite.display_name,
        status=invite.status,
        expires_at=invite.expires_at,
    )


@router.post("/{invite_code}/accept", status_code=204)
async def accept_invite(
    invite_code: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await IdentityService(db).accept_phone_invite(user, invite_code)
