import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.models import Donation, User
from app.schemas import DonationCheckoutRequest, DonationCheckoutResponse


class DonationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_checkout(
        self, user: User | None, body: DonationCheckoutRequest
    ) -> DonationCheckoutResponse:
        if not settings.stripe_secret_key:
            raise ValidationError("Donations are not configured")
        stripe.api_key = settings.stripe_secret_key

        donation = Donation(
            user_id=user.id if user and not body.is_anonymous else None,
            amount_cents=body.amount_cents,
            currency=body.currency,
            is_anonymous=body.is_anonymous,
            status="pending",
        )
        self.db.add(donation)
        await self.db.flush()

        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": body.currency,
                        "unit_amount": body.amount_cents,
                        "product_data": {"name": "YouHoo Alert donation"},
                    },
                    "quantity": 1,
                }
            ],
            success_url=settings.stripe_donation_success_url,
            cancel_url=settings.stripe_donation_cancel_url,
            metadata={"donation_id": str(donation.id)},
        )
        donation.stripe_session_id = session.id
        await self.db.flush()
        return DonationCheckoutResponse(checkout_url=session.url, session_id=session.id)
