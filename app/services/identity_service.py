import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import UserAccountStatus
from app.common.phone import normalize_phone_e164, sanitize_display_name
from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError, ValidationError
from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.models import PhoneInvite, PhoneOtpSession, RefreshToken, TrustedContact, User
from app.repositories.user_repository import UserRepository
from app.schemas import OnboardingStatus, TokenPair
from app.services.group_invite_helpers import ensure_group_invite_for_phone, ensure_group_invite_for_user
from app.services.firebase_auth_service import verify_firebase_id_token


def _is_placeholder_name(name: str | None) -> bool:
    if not name:
        return True
    stripped = name.strip()
    return not stripped or stripped.startswith("User ")


def build_onboarding_status(user: User) -> OnboardingStatus:
    status = user.account_status or UserAccountStatus.REGISTERED.value
    needs_profile = status in {
        UserAccountStatus.REGISTERED.value,
        UserAccountStatus.PROFILE_PENDING.value,
    } or _is_placeholder_name(user.full_name)
    needs_contacts = status in {
        UserAccountStatus.REGISTERED.value,
        UserAccountStatus.PROFILE_PENDING.value,
        UserAccountStatus.PROFILE_COMPLETE.value,
        UserAccountStatus.CONTACTS_PENDING.value,
    }
    onboarding_complete = status == UserAccountStatus.ACTIVE.value and user.phone_verified

    return OnboardingStatus(
        needs_phone_verification=not user.phone_verified,
        needs_profile_setup=needs_profile,
        needs_contacts_permission=needs_contacts,
        onboarding_complete=onboarding_complete,
        account_status=status,
    )


class IdentityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)

    async def firebase_login(self, firebase_id_token: str) -> tuple[User, TokenPair, OnboardingStatus]:
        claims = verify_firebase_id_token(firebase_id_token)
        uid = claims.get("uid") or claims.get("sub")
        if not uid:
            raise UnauthorizedError("Invalid Firebase token payload")

        email = (claims.get("email") or "").lower() or None
        firebase_phone = claims.get("phone_number")
        e164 = normalize_phone_e164(firebase_phone) if firebase_phone else None

        user = await self.users.get_by_firebase_uid(uid)
        if not user and e164:
            user = await self.users.get_by_phone(e164)
        if not user and email:
            user = await self.users.get_by_email(email)

        if not user:
            if e164:
                user = User(
                    full_name=f"User {e164[-4:]}",
                    email=email,
                    firebase_uid=uid,
                    phone_number=e164,
                    phone_verified=True,
                    is_verified=True,
                    account_status=UserAccountStatus.REGISTERED.value,
                    profile_photo=claims.get("picture"),
                )
            elif email:
                user = User(
                    full_name=claims.get("name") or email.split("@")[0],
                    email=email,
                    firebase_uid=uid,
                    google_sub=uid,
                    is_verified=bool(claims.get("email_verified")),
                    profile_photo=claims.get("picture"),
                    account_status=UserAccountStatus.PROFILE_PENDING.value,
                )
            else:
                raise ValidationError("Firebase account must include a verified phone number")
            await self.users.create(user)
            if e164:
                await self._link_pending_invites(user, e164)
        else:
            user.firebase_uid = uid
            if claims.get("name") and _is_placeholder_name(user.full_name):
                user.full_name = claims["name"]
            if claims.get("picture") and not user.profile_photo:
                user.profile_photo = claims["picture"]
            if email and not user.email:
                user.email = email
            if e164:
                existing = await self.users.get_by_phone(e164)
                if existing and existing.id != user.id:
                    raise ConflictError("This mobile number is already registered")
                user.phone_number = e164
                user.phone_verified = True
                if user.account_status == UserAccountStatus.REGISTERED.value:
                    pass
                elif _is_placeholder_name(user.full_name):
                    user.account_status = UserAccountStatus.PROFILE_PENDING.value
            if email:
                user.is_verified = bool(claims.get("email_verified", user.is_verified))
            await self.users.update(user)
            if e164 and user.phone_verified:
                await self._link_pending_invites(user, e164)

        if user.suspended:
            raise ForbiddenError("Account suspended")

        now = datetime.now(UTC)
        user.last_login_at = now
        user.last_active_at = now
        await self.users.update(user)
        tokens = await self._issue_tokens(user)
        return user, tokens, build_onboarding_status(user)

    async def start_phone_login(
        self, phone_number: str, country_code: str | None = None
    ) -> tuple[uuid.UUID, str | None]:
        region = (country_code or "IE").upper()
        e164 = normalize_phone_e164(phone_number, region)
        if not e164:
            raise ValidationError("Enter a valid mobile number")

        otp = f"{secrets.randbelow(900000) + 100000:06d}"
        otp_hash = hash_password(otp)
        expires_at = datetime.now(UTC) + timedelta(minutes=10)

        await self.db.execute(
            delete(PhoneOtpSession).where(
                PhoneOtpSession.user_id.is_(None),
                PhoneOtpSession.phone_number == e164,
            )
        )
        session = PhoneOtpSession(
            user_id=None,
            phone_number=e164,
            otp_hash=otp_hash,
            expires_at=expires_at,
        )
        self.db.add(session)
        await self.db.flush()

        dev_hint = otp if settings.expose_dev_otp else None
        return session.id, dev_hint

    async def verify_phone_login(
        self, phone_number: str, otp: str, country_code: str | None = None
    ) -> tuple[User, TokenPair, OnboardingStatus]:
        region = (country_code or "IE").upper()
        e164 = normalize_phone_e164(phone_number, region)
        if not e164:
            raise ValidationError("Enter a valid mobile number")

        result = await self.db.execute(
            select(PhoneOtpSession)
            .where(
                PhoneOtpSession.user_id.is_(None),
                PhoneOtpSession.phone_number == e164,
            )
            .order_by(PhoneOtpSession.created_at.desc())
        )
        session = result.scalars().first()
        if not session:
            raise ValidationError("Start phone verification first")
        if session.expires_at < datetime.now(UTC):
            raise ValidationError("Verification code expired. Request a new one.")
        if session.attempts >= 5:
            raise ValidationError("Too many attempts. Request a new code.")

        session.attempts += 1
        if not verify_password(otp.strip(), session.otp_hash):
            raise ValidationError("Invalid verification code")

        user = await self.users.get_by_phone(e164)
        now = datetime.now(UTC)
        if user:
            user.last_login_at = now
            user.last_active_at = now
            user.country_code = region
            await self.users.update(user)
        else:
            user = User(
                full_name=f"User {e164[-4:]}",
                email=None,
                phone_number=e164,
                phone_verified=True,
                country_code=region,
                is_verified=True,
                account_status=UserAccountStatus.REGISTERED.value,
                last_login_at=now,
                last_active_at=now,
            )
            await self.users.create(user)
            await self._link_pending_invites(user, e164)

        await self.db.execute(
            delete(PhoneOtpSession).where(
                PhoneOtpSession.user_id.is_(None),
                PhoneOtpSession.phone_number == e164,
            )
        )

        if user.suspended:
            raise ForbiddenError("Account suspended")

        tokens = await self._issue_tokens(user)
        return user, tokens, build_onboarding_status(user)

    async def start_phone_verification(
        self, user: User, phone_number: str, country_code: str | None = None
    ) -> tuple[uuid.UUID, str | None]:
        if user.phone_verified:
            raise ValidationError("Phone number already verified")

        region = (country_code or "IE").upper()
        e164 = normalize_phone_e164(phone_number, region)
        if not e164:
            raise ValidationError("Enter a valid mobile number")

        existing = await self.users.get_by_phone(e164)
        if existing and existing.id != user.id:
            raise ConflictError("This mobile number is already registered")

        otp = f"{secrets.randbelow(900000) + 100000:06d}"
        otp_hash = hash_password(otp)
        expires_at = datetime.now(UTC) + timedelta(minutes=10)

        await self.db.execute(delete(PhoneOtpSession).where(PhoneOtpSession.user_id == user.id))
        session = PhoneOtpSession(
            user_id=user.id,
            phone_number=e164,
            otp_hash=otp_hash,
            expires_at=expires_at,
        )
        self.db.add(session)
        await self.db.flush()

        dev_hint = otp if settings.expose_dev_otp else None
        return session.id, dev_hint

    async def verify_phone_otp(self, user: User, phone_number: str, otp: str, country_code: str | None = None) -> User:
        region = (country_code or "IE").upper()
        e164 = normalize_phone_e164(phone_number, region)
        if not e164:
            raise ValidationError("Enter a valid mobile number")

        result = await self.db.execute(
            select(PhoneOtpSession)
            .where(PhoneOtpSession.user_id == user.id)
            .order_by(PhoneOtpSession.created_at.desc())
        )
        session = result.scalars().first()
        if not session or session.phone_number != e164:
            raise ValidationError("Start phone verification first")
        if session.expires_at < datetime.now(UTC):
            raise ValidationError("Verification code expired. Request a new one.")
        if session.attempts >= 5:
            raise ValidationError("Too many attempts. Request a new code.")

        session.attempts += 1
        if not verify_password(otp.strip(), session.otp_hash):
            raise ValidationError("Invalid verification code")

        existing = await self.users.get_by_phone(e164)
        if existing and existing.id != user.id:
            raise ConflictError("This mobile number is already registered")

        user.phone_number = e164
        user.phone_verified = True
        user.country_code = region
        if user.account_status == UserAccountStatus.REGISTERED.value:
            user.account_status = UserAccountStatus.PROFILE_PENDING.value
        await self.users.update(user)
        await self._link_pending_invites(user, e164)
        await self.db.execute(delete(PhoneOtpSession).where(PhoneOtpSession.user_id == user.id))
        return user

    async def verify_phone_with_firebase_token(self, user: User, firebase_id_token: str) -> User:
        claims = verify_firebase_id_token(firebase_id_token)
        if claims.get("uid") != user.firebase_uid and claims.get("sub") != user.firebase_uid:
            raise UnauthorizedError("Firebase token does not match signed-in user")

        firebase_phone = claims.get("phone_number")
        if not firebase_phone:
            raise ValidationError("Phone number not verified in Firebase yet")

        e164 = normalize_phone_e164(firebase_phone)
        if not e164:
            raise ValidationError("Invalid phone number from Firebase")

        existing = await self.users.get_by_phone(e164)
        if existing and existing.id != user.id:
            raise ConflictError("This mobile number is already registered")

        user.phone_number = e164
        user.phone_verified = True
        if user.account_status == UserAccountStatus.REGISTERED.value:
            user.account_status = UserAccountStatus.PROFILE_PENDING.value
        await self.users.update(user)
        await self._link_pending_invites(user, e164)
        return user

    async def match_contacts(
        self, user: User, contacts: list[dict[str, str | None]], default_region: str = "IE"
    ) -> dict:
        if not user.phone_verified:
            raise ForbiddenError("Verify your mobile number before matching contacts")

        normalized_inputs: list[tuple[str, str | None]] = []
        seen: set[str] = set()
        for entry in contacts[:500]:
            raw_phone = entry.get("phone") or ""
            display_name = sanitize_display_name(entry.get("display_name"))
            e164 = normalize_phone_e164(raw_phone, default_region)
            if not e164 or e164 in seen or e164 == user.phone_number:
                continue
            seen.add(e164)
            normalized_inputs.append((e164, display_name))

        phones = [phone for phone, _ in normalized_inputs]
        matched_users = await self.users.list_by_phones(phones)
        matched_by_phone = {u.phone_number: u for u in matched_users if u.phone_number}

        trusted_result = await self.db.execute(
            select(TrustedContact).where(TrustedContact.owner_user_id == user.id)
        )
        trusted_ids = {row.contact_user_id for row in trusted_result.scalars().all()}

        matched = []
        unmatched = []
        for e164, display_name in normalized_inputs:
            matched_user = matched_by_phone.get(e164)
            if matched_user:
                matched.append(
                    {
                        "user_id": matched_user.id,
                        "display_name": matched_user.full_name,
                        "email": matched_user.email,
                        "phone_last4": e164[-4:],
                        "is_trusted": matched_user.id in trusted_ids,
                        "contact_label": display_name,
                    }
                )
            else:
                unmatched.append({"phone_last4": e164[-4:], "display_name": display_name})

        return {
            "matched_users": matched,
            "unmatched_contacts": unmatched,
            "existing_trusted_contact_ids": list(trusted_ids),
        }

    async def add_trusted_contact(self, user: User, contact_user_id: uuid.UUID, display_name: str | None) -> None:
        if not user.phone_verified:
            raise ForbiddenError("Verify your mobile number first")
        if contact_user_id == user.id:
            raise ValidationError("You cannot add yourself as a trusted contact")

        contact_user = await self.users.get_by_id(contact_user_id)
        if not contact_user or not contact_user.phone_verified:
            raise NotFoundError("Contact not found")

        existing = await self.db.execute(
            select(TrustedContact).where(
                TrustedContact.owner_user_id == user.id,
                TrustedContact.contact_user_id == contact_user_id,
            )
        )
        if existing.scalar_one_or_none():
            return

        self.db.add(
            TrustedContact(
                owner_user_id=user.id,
                contact_user_id=contact_user_id,
                display_name=sanitize_display_name(display_name) or contact_user.full_name,
                status="accepted",
                source="contacts",
            )
        )

    async def create_phone_invite(
        self,
        user: User,
        phone_number: str,
        display_name: str | None = None,
        group_id: uuid.UUID | None = None,
        country_code: str | None = None,
    ) -> PhoneInvite:
        if not user.phone_verified:
            raise ForbiddenError("Verify your mobile number first")

        region = (country_code or "IE").upper()
        e164 = normalize_phone_e164(phone_number, region)
        if not e164:
            raise ValidationError("Enter a valid mobile number")

        existing_user = await self.users.get_by_phone(e164)
        if existing_user:
            if group_id:
                await ensure_group_invite_for_user(
                    self.db,
                    inviter_id=user.id,
                    group_id=group_id,
                    target_user_id=existing_user.id,
                )
                raise ValidationError(
                    "This person is already on YouHoo Alert. A group invitation has been sent."
                )
            await self.add_trusted_contact(user, existing_user.id, display_name)
            raise ValidationError(
                "This person is already on YouHoo Alert. They have been added to your trusted contacts."
            )

        invite_code = secrets.token_urlsafe(12)
        invite = PhoneInvite(
            inviter_user_id=user.id,
            invited_phone_number=e164,
            display_name=sanitize_display_name(display_name),
            invite_code=invite_code,
            group_id=group_id,
            expires_at=datetime.now(UTC) + timedelta(days=14),
        )
        self.db.add(invite)
        await self.db.flush()

        if group_id:
            await ensure_group_invite_for_phone(
                self.db,
                inviter_id=user.id,
                group_id=group_id,
                phone_e164=e164,
            )

        return invite

    async def get_invite_by_code(self, invite_code: str) -> PhoneInvite:
        result = await self.db.execute(
            select(PhoneInvite).where(PhoneInvite.invite_code == invite_code)
        )
        invite = result.scalar_one_or_none()
        if not invite:
            raise NotFoundError("Invite not found")
        return invite

    async def accept_phone_invite(self, user: User, invite_code: str) -> None:
        if not user.phone_verified or not user.phone_number:
            raise ForbiddenError("Verify your mobile number before accepting invites")

        invite = await self.get_invite_by_code(invite_code)
        if invite.status != "pending":
            raise ValidationError("Invite is no longer active")
        if invite.expires_at and invite.expires_at < datetime.now(UTC):
            invite.status = "expired"
            raise ValidationError("Invite has expired")
        if invite.invited_phone_number != user.phone_number:
            raise ForbiddenError("This invite was sent to a different mobile number")

        invite.status = "accepted"
        invite.accepted_at = datetime.now(UTC)

        self.db.add(
            TrustedContact(
                owner_user_id=invite.inviter_user_id,
                contact_user_id=user.id,
                display_name=user.full_name,
                status="accepted",
                source="invite",
            )
        )
        inviter = await self.users.get_by_id(invite.inviter_user_id)
        inviter_name = inviter.full_name if inviter else "Contact"

        self.db.add(
            TrustedContact(
                owner_user_id=user.id,
                contact_user_id=invite.inviter_user_id,
                display_name=invite.display_name or inviter_name,
                status="accepted",
                source="invite",
            )
        )

        if invite.group_id:
            from app.models import GroupMember

            existing = await self.db.execute(
                select(GroupMember).where(
                    GroupMember.group_id == invite.group_id,
                    GroupMember.user_id == user.id,
                )
            )
            if not existing.scalar_one_or_none():
                self.db.add(GroupMember(group_id=invite.group_id, user_id=user.id, role="member"))

    async def _link_pending_invites(self, user: User, e164: str) -> None:
        result = await self.db.execute(
            select(PhoneInvite).where(
                PhoneInvite.invited_phone_number == e164,
                PhoneInvite.status == "pending",
            )
        )
        for invite in result.scalars().all():
            if invite.group_id:
                await ensure_group_invite_for_phone(
                    self.db,
                    inviter_id=invite.inviter_user_id,
                    group_id=invite.group_id,
                    phone_e164=e164,
                )

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
