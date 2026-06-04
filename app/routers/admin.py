from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import require_admin
from app.schemas.admin import (
    AdminEmergencyResponse,
    AdminReportResponse,
    AdminReportStatusUpdate,
    AdminUserResponse,
    AdminUserSuspendUpdate,
)
from app.schemas.emergency import EmergencyResponse
from app.schemas.user import ErrorResponse
from app.services import store

router = APIRouter(prefix="/admin", tags=["admin"])


def _emergency_response(emergency: store.Emergency) -> EmergencyResponse:
    return EmergencyResponse(**emergency.to_dict())


@router.get("/emergencies", response_model=list[AdminEmergencyResponse])
def list_emergencies(
    auth: Annotated[tuple, Depends(require_admin)],
) -> list[AdminEmergencyResponse]:
    db, _, _ = auth
    return [
        AdminEmergencyResponse(
            id=e.id,
            userId=e.user_id,
            userName=e.user_name,
            status=e.status,
            startedAt=e.started_at,
            lat=e.lat,
            lng=e.lng,
            contactsCount=e.contacts_count,
        )
        for e in store.list_admin_emergencies(db)
    ]


@router.patch("/emergencies/{emergency_id}", response_model=EmergencyResponse)
def resolve_emergency(
    emergency_id: str,
    auth: Annotated[tuple, Depends(require_admin)],
) -> EmergencyResponse:
    db, _, _ = auth
    emergency = store.admin_resolve_emergency(db, emergency_id)
    if not emergency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(error="Emergency not found").model_dump(),
        )
    return _emergency_response(emergency)


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    auth: Annotated[tuple, Depends(require_admin)],
) -> list[AdminUserResponse]:
    db, _, _ = auth
    return [
        AdminUserResponse(
            id=u.id,
            name=u.name,
            email=u.email,
            suspended=u.suspended,
            emergencies=u.emergencies,
        )
        for u in store.list_admin_users(db)
    ]


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
def update_user(
    user_id: str,
    body: AdminUserSuspendUpdate,
    auth: Annotated[tuple, Depends(require_admin)],
) -> AdminUserResponse:
    db, _, _ = auth
    user = store.set_user_suspended(db, user_id, body.suspended)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(error="User not found").model_dump(),
        )
    users = store.list_admin_users(db)
    summary = next((u for u in users if u.id == user_id), None)
    emergencies = summary.emergencies if summary else 0
    return AdminUserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        suspended=user.suspended,
        emergencies=emergencies,
    )


@router.get("/reports", response_model=list[AdminReportResponse])
def list_reports(
    auth: Annotated[tuple, Depends(require_admin)],
) -> list[AdminReportResponse]:
    return []


@router.patch("/reports/{report_id}", response_model=AdminReportResponse)
def update_report(
    report_id: str,
    body: AdminReportStatusUpdate,
    auth: Annotated[tuple, Depends(require_admin)],
) -> AdminReportResponse:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=ErrorResponse(error="Report not found").model_dump(),
    )
