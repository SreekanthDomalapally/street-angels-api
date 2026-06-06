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
    DeviceTokenRequest,
    GoogleAuthRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


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
