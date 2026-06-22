import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import TripStatus
from app.core.config import settings
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models import AuditLog, Trip, User
from app.repositories.group_repository import GroupRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.user_repository import UserRepository
from app.schemas import ALLOWED_TRIP_DURATIONS, LocationUpdateRequest, TripCreateRequest, TripOut
from app.services.notification_queue import NotificationQueue

logger = get_logger(__name__)

ARRIVAL_RADIUS_METERS = 150


class TripService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.trips = TripRepository(db)
        self.groups = GroupRepository(db)
        self.users = UserRepository(db)
        self.queue = NotificationQueue()
        self._last_location_at: dict[UUID, datetime] = {}

    async def create(self, user: User, body: TripCreateRequest) -> TripOut:
        if body.duration_minutes not in ALLOWED_TRIP_DURATIONS:
            raise ValidationError("duration_minutes must be one of 30, 60, 120, 240")

        if not await self.groups.is_member(body.group_id, user.id):
            raise ForbiddenError("You are not a member of this group")

        existing = await self.trips.get_active_for_traveler(user.id)
        if existing:
            raise ValidationError("You already have an active trip watch")

        if body.destination_latitude is not None or body.destination_longitude is not None:
            if body.destination_latitude is None or body.destination_longitude is None:
                raise ValidationError("Both destination latitude and longitude are required")
            self._validate_location(body.destination_latitude, body.destination_longitude)

        if body.latitude is not None and body.longitude is not None:
            self._validate_location(body.latitude, body.longitude, body.accuracy_meters)

        now = datetime.now(UTC)
        trip = Trip(
            group_id=body.group_id,
            traveler_user_id=user.id,
            label=body.label,
            status=TripStatus.ACTIVE.value,
            duration_minutes=body.duration_minutes,
            destination_latitude=body.destination_latitude,
            destination_longitude=body.destination_longitude,
            destination_label=body.destination_label,
            current_latitude=body.latitude,
            current_longitude=body.longitude,
            accuracy_meters=body.accuracy_meters,
            started_at=now,
            expires_at=now + timedelta(minutes=body.duration_minutes),
        )
        await self.trips.create(trip)
        await self._audit(user.id, "trip.create", str(trip.id))

        member_ids = await self._group_member_ids(body.group_id)
        await self.queue.enqueue_trip_started(
            trip_id=str(trip.id),
            group_id=str(body.group_id),
            traveler_name=user.full_name,
            label=body.label or "Trip watch",
            recipient_user_ids=[str(uid) for uid in member_ids if uid != user.id],
        )
        logger.info("trip_created", extra={"trip_id": str(trip.id), "user_id": str(user.id)})
        return await self._to_out(await self.trips.get_by_id(trip.id) or trip)

    async def get_active_mine(self, user: User) -> TripOut:
        trip = await self.trips.get_active_for_traveler(user.id)
        if not trip:
            raise NotFoundError("No active trip watch")
        await self._maybe_expire(trip)
        return await self._to_out(trip)

    async def get(self, user: User, trip_id: UUID) -> TripOut:
        trip = await self._require_trip_access(user, trip_id)
        await self._maybe_expire(trip)
        return await self._to_out(trip)

    async def list_active_for_group(self, user: User, group_id: UUID) -> list[TripOut]:
        if not await self.groups.is_member(group_id, user.id):
            raise ForbiddenError("You are not a member of this group")
        trips = await self.trips.list_active_for_group(group_id)
        results: list[TripOut] = []
        for trip in trips:
            await self._maybe_expire(trip)
            if trip.status == TripStatus.ACTIVE.value:
                results.append(await self._to_out(trip))
        return results

    async def update_location(
        self, user: User, trip_id: UUID, body: LocationUpdateRequest
    ) -> TripOut:
        trip = await self._require_traveler(trip_id, user.id)
        if trip.status != TripStatus.ACTIVE.value:
            raise ValidationError("Trip is not active")
        self._validate_location(body.latitude, body.longitude, body.accuracy_meters)
        self._throttle_location(trip.id)

        trip.current_latitude = body.latitude
        trip.current_longitude = body.longitude
        trip.accuracy_meters = body.accuracy_meters
        user.last_known_latitude = body.latitude
        user.last_known_longitude = body.longitude
        await self.users.update(user)
        await self.trips.update(trip)

        if (
            trip.destination_latitude is not None
            and trip.destination_longitude is not None
            and self._within_arrival_radius(
                body.latitude,
                body.longitude,
                trip.destination_latitude,
                trip.destination_longitude,
            )
        ):
            return await self.arrive(user, trip_id)

        return await self._to_out(trip)

    async def arrive(self, user: User, trip_id: UUID) -> TripOut:
        trip = await self._require_traveler(trip_id, user.id)
        if trip.status not in {TripStatus.ACTIVE.value}:
            raise ValidationError("Trip is not active")
        trip.status = TripStatus.ARRIVED.value
        trip.arrived_at = datetime.now(UTC)
        await self.trips.update(trip)
        await self._audit(user.id, "trip.arrive", str(trip.id))

        member_ids = await self._group_member_ids(trip.group_id)
        await self.queue.enqueue_trip_arrived(
            trip_id=str(trip.id),
            group_id=str(trip.group_id),
            traveler_name=user.full_name,
            destination_label=trip.destination_label or "destination",
            recipient_user_ids=[str(uid) for uid in member_ids if uid != user.id],
        )
        return await self._to_out(trip)

    async def end(self, user: User, trip_id: UUID) -> TripOut:
        trip = await self._require_traveler(trip_id, user.id)
        if trip.status in {TripStatus.ENDED.value, TripStatus.EXPIRED.value}:
            return await self._to_out(trip)
        trip.status = TripStatus.ENDED.value
        trip.ended_at = datetime.now(UTC)
        await self.trips.update(trip)
        await self._audit(user.id, "trip.end", str(trip.id))
        return await self._to_out(trip)

    async def _require_trip_access(self, user: User, trip_id: UUID) -> Trip:
        trip = await self.trips.get_by_id(trip_id)
        if not trip:
            raise NotFoundError("Trip not found")
        if trip.traveler_user_id == user.id:
            return trip
        if await self.groups.is_member(trip.group_id, user.id):
            return trip
        raise ForbiddenError("No access to this trip")

    async def _require_traveler(self, trip_id: UUID, user_id: UUID) -> Trip:
        trip = await self.trips.get_by_id(trip_id)
        if not trip:
            raise NotFoundError("Trip not found")
        if trip.traveler_user_id != user_id:
            raise ForbiddenError("Only the traveler can perform this action")
        return trip

    async def _maybe_expire(self, trip: Trip) -> None:
        if trip.status != TripStatus.ACTIVE.value:
            return
        expires = trip.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if datetime.now(UTC) >= expires:
            trip.status = TripStatus.EXPIRED.value
            trip.ended_at = datetime.now(UTC)
            await self.trips.update(trip)

    async def _to_out(self, trip: Trip) -> TripOut:
        group_name = trip.group.name if trip.group else None
        traveler_name = trip.traveler.full_name if trip.traveler else None
        return TripOut(
            id=trip.id,
            group_id=trip.group_id,
            group_name=group_name,
            label=trip.label,
            status=TripStatus(trip.status),
            destination_latitude=trip.destination_latitude,
            destination_longitude=trip.destination_longitude,
            destination_label=trip.destination_label,
            current_latitude=trip.current_latitude,
            current_longitude=trip.current_longitude,
            accuracy_meters=trip.accuracy_meters,
            started_at=trip.started_at,
            expires_at=trip.expires_at,
            arrived_at=trip.arrived_at,
            ended_at=trip.ended_at,
            traveler_user_id=trip.traveler_user_id,
            traveler_name=traveler_name,
        )

    async def _group_member_ids(self, group_id: UUID) -> list[UUID]:
        group = await self.groups.get_by_id(group_id)
        if not group:
            return []
        return [m.user_id for m in group.members]

    async def _audit(self, user_id: UUID, action: str, resource_id: str) -> None:
        self.db.add(
            AuditLog(
                user_id=user_id,
                action=action,
                resource_type="trip",
                resource_id=resource_id,
            )
        )

    def _throttle_location(self, trip_id: UUID) -> None:
        now = datetime.now(UTC)
        last = self._last_location_at.get(trip_id)
        if last:
            elapsed = (now - last).total_seconds()
            if elapsed < settings.location_min_update_seconds:
                raise ValidationError(
                    f"Location updates throttled to every {settings.location_min_update_seconds}s"
                )
        self._last_location_at[trip_id] = now

    def _validate_location(
        self, lat: float, lng: float, accuracy: float | None = None
    ) -> None:
        if abs(lat) > 90 or abs(lng) > 180:
            raise ValidationError("Invalid coordinates")
        if lat == 0.0 and lng == 0.0:
            raise ValidationError("Invalid location (0,0)")
        if accuracy is not None and accuracy > settings.location_max_accuracy_meters:
            raise ValidationError("Location accuracy too low")

    @staticmethod
    def _within_arrival_radius(
        lat1: float, lon1: float, lat2: float, lon2: float, radius_m: float = ARRIVAL_RADIUS_METERS
    ) -> bool:
        r = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        distance = 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return distance <= radius_m
