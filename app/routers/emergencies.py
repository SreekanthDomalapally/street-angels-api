from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import require_user
from app.schemas.emergency import ActiveEmergencyResponse, EmergencyResponse, EmergencyUpdate
from app.schemas.user import ErrorResponse
from app.services import store

router = APIRouter(prefix="/emergencies", tags=["emergencies"])


def _emergency_response(emergency: store.Emergency) -> EmergencyResponse:
    return EmergencyResponse(**emergency.to_dict())


@router.post("", response_model=EmergencyResponse, status_code=status.HTTP_201_CREATED)
def create_emergency(
    auth: Annotated[tuple, Depends(require_user)],
) -> EmergencyResponse:
    db, user_id, _ = auth
    return _emergency_response(store.create_emergency(db, user_id))


@router.get("/active", response_model=ActiveEmergencyResponse)
def active_emergency(
    auth: Annotated[tuple, Depends(require_user)],
) -> ActiveEmergencyResponse:
    db, user_id, _ = auth
    emergency = store.get_active_emergency(db, user_id)
    return ActiveEmergencyResponse(
        emergency=_emergency_response(emergency) if emergency else None
    )


@router.patch("/{emergency_id}", response_model=EmergencyResponse)
def patch_emergency(
    emergency_id: str,
    body: EmergencyUpdate,
    auth: Annotated[tuple, Depends(require_user)],
) -> EmergencyResponse:
    db, user_id, _ = auth
    status_value: Literal["resolved", "cancelled"] | None = None
    if body.status in ("resolved", "cancelled"):
        status_value = body.status

    emergency = store.update_emergency(db, user_id, emergency_id, status=status_value)
    if not emergency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(error="Emergency not found").model_dump(),
        )
    return _emergency_response(emergency)
