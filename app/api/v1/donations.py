from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_optional_user
from app.db.session import get_db
from app.models import User
from app.schemas import DonationCheckoutRequest, DonationCheckoutResponse
from app.services.donation_service import DonationService

router = APIRouter(prefix="/donations", tags=["donations"])


@router.post("/checkout", response_model=DonationCheckoutResponse)
async def create_donation_checkout(
    body: DonationCheckoutRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_user)],
) -> DonationCheckoutResponse:
    return await DonationService(db).create_checkout(user, body)
