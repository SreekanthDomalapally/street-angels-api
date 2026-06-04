from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import require_user, user_response
from app.schemas.user import ErrorResponse, UserResponse, UserUpdate
from app.services import store

router = APIRouter(prefix="/users", tags=["users"])


@router.patch("/me", response_model=UserResponse)
def update_me(
    body: UserUpdate,
    auth: Annotated[tuple, Depends(require_user)],
) -> UserResponse:
    db, user_id, _ = auth
    user = store.update_user(
        db,
        user_id,
        name=body.name,
        emergency_phrase=body.emergencyPhrase,
        emergency_phrase_set="emergencyPhrase" in body.model_fields_set,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(error="User not found").model_dump(),
        )
    return user_response(user)
