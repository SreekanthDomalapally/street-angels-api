from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models import User
from app.schemas import (
    ContactMatchRequest,
    ContactMatchResponse,
    DeviceTokenRequest,
    FirebaseLoginRequest,
    FirebaseLoginResponse,
    GoogleAuthRequest,
    LoginRequest,
    OnboardingStatus,
    PhoneFirebaseVerifyRequest,
    PhoneStartRequest,
    PhoneStartResponse,
    PhoneVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    TrustedContactAddRequest,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.services.identity_service import IdentityService, build_onboarding_status

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/firebase-login", response_model=FirebaseLoginResponse)
@limiter.limit(settings.auth_rate_limit)
async def firebase_login(
    request: Request,
    body: FirebaseLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FirebaseLoginResponse:
    user, tokens, onboarding = await IdentityService(db).firebase_login(body.firebase_id_token)
    return FirebaseLoginResponse(user=user, onboarding=onboarding, **tokens.model_dump())


@router.post("/phone/start", response_model=PhoneStartResponse)
@limiter.limit("5/minute")
async def phone_start(
    request: Request,
    body: PhoneStartRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhoneStartResponse:
    session_id, dev_otp = await IdentityService(db).start_phone_verification(
        user, body.phone_number, body.country_code
    )
    return PhoneStartResponse(session_id=session_id, dev_otp=dev_otp)


@router.post("/phone/verify", response_model=UserResponse)
@limiter.limit("10/minute")
async def phone_verify(
    request: Request,
    body: PhoneVerifyRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    return await IdentityService(db).verify_phone_otp(
        user, body.phone_number, body.otp, body.country_code
    )


@router.post("/phone/verify-firebase", response_model=UserResponse)
@limiter.limit(settings.auth_rate_limit)
async def phone_verify_firebase(
    request: Request,
    body: PhoneFirebaseVerifyRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    return await IdentityService(db).verify_phone_with_firebase_token(
        user, body.firebase_id_token
    )


@router.get("/onboarding", response_model=OnboardingStatus)
async def onboarding_status(user: Annotated[User, Depends(get_current_user)]) -> OnboardingStatus:
    return build_onboarding_status(user)


@router.post("/register", response_model=TokenPair)
@limiter.limit(settings.auth_rate_limit)
async def register(
    request: Request,
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    _, tokens = await AuthService(db).register(body)
    return tokens


@router.post("/login", response_model=TokenPair)
@limiter.limit(settings.auth_rate_limit)
async def login(
    request: Request,
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    _, tokens = await AuthService(db).login(body)
    return tokens


@router.post("/google", response_model=TokenPair)
@limiter.limit(settings.auth_rate_limit)
async def google_auth(
    request: Request,
    body: GoogleAuthRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    _, tokens = await AuthService(db).google_login(body)
    return tokens


@router.post("/refresh", response_model=TokenPair)
@limiter.limit(settings.auth_rate_limit)
async def refresh(
    request: Request,
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    return await AuthService(db).refresh(body.refresh_token)


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user


@router.post("/devices", status_code=204)
async def register_device(
    body: DeviceTokenRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await AuthService(db).register_device(user, body)
