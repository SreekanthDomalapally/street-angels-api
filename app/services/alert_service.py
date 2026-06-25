from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import AlertStatus
from app.core.config import settings
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models import (
    Alert,
    AlertEvent,
    AlertLocationUpdate,
    AlertRecipient,
    AlertResponse,
    AuditLog,
    User,
)
from app.repositories.alert_repository import AlertRepository
from app.repositories.group_repository import GroupRepository
from app.repositories.user_repository import UserRepository
from app.schemas import AlertCreateRequest, AlertResponseRequest, LocationUpdateRequest
from app.common.emergency_types import severity_for
from app.services.notification_outbox import NotificationOutbox
from app.services.notification_queue import NotificationQueue
from app.services.routing_service import RoutingService
from app.websocket.manager import alert_ws_manager

logger = get_logger(__name__)


class AlertService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.alerts = AlertRepository(db)
        self.groups = GroupRepository(db)
        self.users = UserRepository(db)
        self.queue = NotificationQueue()
        self.outbox = NotificationOutbox(db)
        self.routing = RoutingService(db)

    async def create(self, user: User, body: AlertCreateRequest) -> Alert:
        correlation_id = str(uuid4())
        logger.info(
            "SOS_TRIGGERED",
            extra={
                "correlation_id": correlation_id,
                "sender_user_id": str(user.id),
                "group_id": str(body.group_id),
                "alert_type": body.alert_type.value,
            },
        )
        if not user.phone_verified:
            raise ValidationError("Verify your phone number before sending SOS alerts.")
        recent = await self.alerts.recent_active_by_user(
            user.id, within_seconds=settings.sos_cooldown_seconds
        )
        if recent:
            raise ValidationError(
                f"Please wait {settings.sos_cooldown_seconds}s before sending another SOS."
            )
        if not await self.groups.is_member(body.group_id, user.id):
            raise ForbiddenError("You are not a member of this group")
        self._validate_location(body.latitude, body.longitude)

        alert = Alert(
            created_by=user.id,
            group_id=body.group_id,
            alert_type=body.alert_type.value,
            message=body.message,
            latitude=body.latitude,
            longitude=body.longitude,
            status=AlertStatus.ACTIVE.value,
            severity=severity_for(body.alert_type.value),
        )
        await self.alerts.create(alert)
        user.last_known_latitude = body.latitude
        user.last_known_longitude = body.longitude
        user.location_updated_at = datetime.now(UTC)
        await self.users.update(user)

        await self._log_event(alert.id, "alert.created", {"created_by": str(user.id)})
        await self._audit(user.id, "alert.create", str(alert.id))

        # Smart routing: matching groups -> deduped, ranked responders.
        recipients = await self.routing.build_recipients(user, alert)
        if not recipients:
            for member_id in await self._group_member_ids(body.group_id):
                if member_id == user.id:
                    continue
                recipients.append(
                    AlertRecipient(
                        alert_id=alert.id,
                        user_id=member_id,
                        group_id=body.group_id,
                        notified=True,
                        delivery_status="pending",
                    )
                )
        if not recipients:
            recipients = await self._fallback_all_circle_members(user, alert)
        if not recipients:
            raise ValidationError(
                "No reachable contacts in your circles. Add people to a group before sending SOS."
            )
        for recipient in recipients:
            self.db.add(recipient)
        await self.db.flush()

        recipient_ids = [str(r.user_id) for r in recipients]

        logger.info(
            "RECIPIENTS_SELECTED",
            extra={
                "correlation_id": correlation_id,
                "alert_id": str(alert.id),
                "sender_user_id": str(user.id),
                "recipient_count": len(recipient_ids),
                "recipient_user_ids": recipient_ids,
            },
        )

        outbox_payload = {
            "type": "alert_created",
            "priority": "high",
            "correlation_id": correlation_id,
            "alert_id": str(alert.id),
            "group_id": str(body.group_id),
            "alert_type": alert.alert_type,
            "sender_name": user.full_name,
            "sender_user_id": str(user.id),
            "latitude": alert.latitude,
            "longitude": alert.longitude,
            "recipient_user_ids": recipient_ids,
            "recipient_count": len(recipient_ids),
            "alert_created_at": datetime.now(UTC).isoformat(),
            "notification_queued_at": datetime.now(UTC).isoformat(),
        }
        await self.outbox.enqueue_in_transaction(outbox_payload)
        logger.info(
            "NOTIFICATION_QUEUED",
            extra={
                "correlation_id": correlation_id,
                "alert_id": str(alert.id),
                "sender_user_id": str(user.id),
                "recipient_count": len(recipient_ids),
                "recipient_user_ids": recipient_ids,
            },
        )
        await alert_ws_manager.broadcast(
            str(alert.id),
            {"type": "alert_created", "alert_id": str(alert.id), "status": alert.status},
        )
        logger.info(
            "ALERT_CREATED",
            extra={
                "correlation_id": correlation_id,
                "alert_id": str(alert.id),
                "sender_user_id": str(user.id),
                "recipient_count": len(recipient_ids),
                "recipient_user_ids": recipient_ids,
            },
        )
        return alert

    async def respond(self, user: User, alert_id: UUID, body: AlertResponseRequest) -> AlertResponse:
        alert = await self._require_alert_access(user, alert_id)
        if alert.created_by == user.id:
            raise ForbiddenError("Alert creator cannot respond to their own alert")
        if not await self.alerts.is_recipient(alert_id, user.id):
            raise ForbiddenError("Only alert recipients can respond")
        if alert.status != AlertStatus.ACTIVE.value:
            raise ValidationError("Alert is not active")
        distance_km = await self._recipient_distance(alert_id, user.id)
        existing = await self.alerts.get_response(alert_id, user.id)
        if existing:
            existing.response_type = body.response_type.value
            existing.eta_minutes = body.eta_minutes
            if distance_km is not None:
                existing.distance_km = distance_km
            response = existing
        else:
            response = AlertResponse(
                alert_id=alert_id,
                user_id=user.id,
                response_type=body.response_type.value,
                eta_minutes=body.eta_minutes,
                distance_km=distance_km,
            )
            await self.alerts.add_response(response)

        await self._log_event(
            alert_id,
            "alert.response",
            {"user_id": str(user.id), "response_type": body.response_type.value},
        )
        await self.queue.enqueue_alert_response(
            alert_id=str(alert_id),
            creator_id=str(alert.created_by),
            responder_name=user.full_name,
            response_type=body.response_type.value,
        )
        await alert_ws_manager.broadcast(
            str(alert_id),
            {
                "type": "alert_response",
                "user_id": str(user.id),
                "response_type": body.response_type.value,
                "eta_minutes": body.eta_minutes,
            },
        )
        return response

    async def update_location(
        self, user: User, alert_id: UUID, body: LocationUpdateRequest
    ) -> AlertLocationUpdate:
        alert = await self._require_alert_access(user, alert_id)
        if alert.status != AlertStatus.ACTIVE.value:
            raise ValidationError("Alert is not active")
        self._validate_location(body.latitude, body.longitude, body.accuracy_meters)

        result = await self.db.execute(
            select(AlertLocationUpdate)
            .where(AlertLocationUpdate.alert_id == alert_id, AlertLocationUpdate.user_id == user.id)
            .order_by(AlertLocationUpdate.recorded_at.desc())
            .limit(1)
        )
        last = result.scalar_one_or_none()
        if last:
            elapsed = (datetime.now(UTC) - last.recorded_at).total_seconds()
            if elapsed < settings.location_min_update_seconds:
                raise ValidationError(
                    f"Location updates throttled to every {settings.location_min_update_seconds}s"
                )

        update = AlertLocationUpdate(
            alert_id=alert_id,
            user_id=user.id,
            latitude=body.latitude,
            longitude=body.longitude,
            accuracy_meters=body.accuracy_meters,
        )
        await self.alerts.add_location(update)
        user.last_known_latitude = body.latitude
        user.last_known_longitude = body.longitude
        await self.users.update(user)

        payload = {
            "type": "location_update",
            "user_id": str(user.id),
            "latitude": body.latitude,
            "longitude": body.longitude,
            "accuracy_meters": body.accuracy_meters,
            "recorded_at": update.recorded_at.isoformat(),
        }
        await alert_ws_manager.broadcast(str(alert_id), payload)
        return update

    async def resolve(self, user: User, alert_id: UUID) -> Alert:
        alert = await self.alerts.get_by_id(alert_id)
        if not alert:
            raise NotFoundError("Alert not found")
        if alert.created_by != user.id:
            raise ForbiddenError("Only the alert creator can resolve it")
        alert.status = AlertStatus.RESOLVED.value
        alert.resolved_at = datetime.now(UTC)
        await self._log_event(alert_id, "alert.resolved", {"resolved_by": str(user.id)})
        await alert_ws_manager.broadcast(
            str(alert_id),
            {"type": "alert_resolved", "alert_id": str(alert_id), "status": "resolved"},
        )
        return alert

    async def get(self, user: User, alert_id: UUID) -> Alert:
        return await self._require_alert_access(user, alert_id)

    async def require_alert_access(self, user: User, alert_id: UUID) -> Alert:
        return await self._require_alert_access(user, alert_id)

    async def list_for_user(self, user: User, *, limit: int = 50) -> list[Alert]:
        return await self.alerts.list_for_user(user.id, limit=limit)

    async def _require_alert_access(self, user: User, alert_id: UUID) -> Alert:
        alert = await self.alerts.get_by_id(alert_id)
        if not alert:
            raise NotFoundError("Alert not found")
        if alert.created_by == user.id:
            return alert
        if await self.alerts.is_recipient(alert_id, user.id):
            return alert
        raise ForbiddenError("No access to this alert")

    async def _fallback_all_circle_members(self, user: User, alert: Alert) -> list[AlertRecipient]:
        """Last-resort: notify everyone in all of the creator's circles."""
        memberships = await self.groups.list_memberships_for_user(user.id)
        all_group_ids = [m.group_id for m in memberships]
        if not all_group_ids:
            return []
        members = await self.groups.list_members_for_groups(all_group_ids)
        recipients: list[AlertRecipient] = []
        seen: set[UUID] = set()
        for member in members:
            if member.user_id == user.id or member.user_id in seen:
                continue
            if member.user is not None and member.user.suspended:
                continue
            seen.add(member.user_id)
            recipients.append(
                AlertRecipient(
                    alert_id=alert.id,
                    user_id=member.user_id,
                    group_id=member.group_id,
                    notified=True,
                    delivery_status="pending",
                )
            )
        return recipients

    async def _recipient_distance(self, alert_id: UUID, user_id: UUID) -> float | None:
        result = await self.db.execute(
            select(AlertRecipient.distance_km).where(
                AlertRecipient.alert_id == alert_id,
                AlertRecipient.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _group_member_ids(self, group_id: UUID) -> list[UUID]:
        group = await self.groups.get_by_id(group_id)
        if not group:
            return []
        return [m.user_id for m in group.members]

    async def _log_event(self, alert_id: UUID, event_type: str, payload: dict) -> None:
        await self.alerts.log_event(AlertEvent(alert_id=alert_id, event_type=event_type, payload=payload))

    async def _audit(self, user_id: UUID, action: str, resource_id: str) -> None:
        self.db.add(
            AuditLog(
                user_id=user_id,
                action=action,
                resource_type="alert",
                resource_id=resource_id,
            )
        )

    def _validate_location(
        self, lat: float, lng: float, accuracy: float | None = None
    ) -> None:
        if abs(lat) > 90 or abs(lng) > 180:
            raise ValidationError("Invalid coordinates")
        if lat == 0.0 and lng == 0.0:
            raise ValidationError("Invalid location (0,0)")
        if accuracy is not None and accuracy > settings.location_max_accuracy_meters:
            raise ValidationError("Location accuracy too low")
