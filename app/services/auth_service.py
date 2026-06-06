import uuid
from datetime import UTC, datetime, timedelta

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError, ValidationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models import DeviceToken, RefreshToken, User
from app.repositories.user_repository import UserRepository
from app.schemas import DeviceTokenRequest, GoogleAuthRequest, LoginRequest, RegisterRequest, TokenPair


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)

    async def register(self, body: RegisterRequest) -> tuple[User, TokenPair]:
        if await self.users.get_by_email(body.email):
            raise ConflictError("Email already registered")
        user = User(
            full_name=body.full_name.strip(),
            email=body.email.lower(),
            phone_number=body.phone_number,
            password_hash=hash_password(body.password),
            is_verified=False,
        )
        await self.users.create(user)
        tokens = await self._issue_tokens(user)
        return user, tokens

    async def login(self, body: LoginRequest) -> tuple[User, TokenPair]:
        user = await self.users.get_by_email(body.email)
        if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
            raise UnauthorizedError("Invalid email or password")
        self._ensure_active(user)
        tokens = await self._issue_tokens(user)
        return user, tokens

    async def google_login(self, body: GoogleAuthRequest) -> tuple[User, TokenPair]:
        if not settings.google_oauth_client_id:
            raise ValidationError("Google OAuth is not configured")
        try:
            info = id_token.verify_oauth2_token(
                body.id_token, google_requests.Request(), settings.google_oauth_client_id
            )
        except Exception as exc:
            raise UnauthorizedError("Invalid Google token") from exc
        email = info.get("email", "").lower()
        sub = info.get("sub")
        if not email or not sub:
            raise UnauthorizedError("Invalid Google token payload")
        user = await self.users.get_by_google_sub(sub)
        if not user:
            user = await self.users.get_by_email(email)
        if user:
            user.google_sub = sub
            user.is_verified = info.get("email_verified", user.is_verified)
            if not user.full_name and info.get("name"):
                user.full_name = info["name"]
            await self.users.update(user)
        else:
            user = User(
                full_name=info.get("name") or email.split("@")[0],
                email=email,
                google_sub=sub,
                is_verified=bool(info.get("email_verified")),
                profile_photo=info.get("picture"),
            )
            await self.users.create(user)
        self._ensure_active(user)
        tokens = await self._issue_tokens(user)
        return user, tokens

    async def refresh(self, refresh_token: str) -> TokenPair:
        from app.core.security import decode_token

        try:
            payload = decode_token(refresh_token)
        except Exception as exc:
            raise UnauthorizedError("Invalid refresh token") from exc
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid refresh token")
        jti = payload.get("jti")
        user_id = uuid.UUID(payload["sub"])
        from sqlalchemy import select

        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.jti == jti,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
            )
        )
        stored = result.scalar_one_or_none()
        if not stored or stored.expires_at < datetime.now(UTC):
            raise UnauthorizedError("Refresh token expired or revoked")
        user = await self.users.get_by_id(user_id)
        if not user:
            raise UnauthorizedError()
        self._ensure_active(user)
        stored.revoked = True
        return await self._issue_tokens(user)

    async def register_device(self, user: User, body: DeviceTokenRequest) -> None:
        from sqlalchemy import select

        result = await self.db.execute(
            select(DeviceToken).where(DeviceToken.user_id == user.id, DeviceToken.token == body.token)
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.platform = body.platform
            existing.updated_at = datetime.now(UTC)
            return
        self.db.add(
            DeviceToken(user_id=user.id, token=body.token, platform=body.platform)
        )

    def _ensure_active(self, user: User) -> None:
        if user.suspended:
            raise ForbiddenError("Account suspended")

    async def _issue_tokens(self, user: User) -> TokenPair:
        jti = uuid.uuid4().hex
        refresh = RefreshToken(
            user_id=user.id,
            jti=jti,
            expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
        )
        self.db.add(refresh)
        return TokenPair(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id, jti),
        )
