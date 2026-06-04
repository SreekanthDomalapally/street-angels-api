from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import DbSession
from app.schemas.user import ErrorResponse, UserResponse
from app.services import store


def _session_cookie_kwargs() -> dict:
    return {
        "key": settings.session_cookie,
        "httponly": True,
        "path": "/",
        "samesite": "lax",
        "max_age": settings.session_max_age,
    }


def set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(value=session_id, **_session_cookie_kwargs())


def clear_session_cookie(response: Response) -> None:
    response.set_cookie(value="", max_age=0, **_session_cookie_kwargs())


async def require_user(
    db: DbSession,
    sa_session: Annotated[str | None, Cookie(alias="sa_session")] = None,
) -> tuple[Session | None, str, store.User]:
    if not sa_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse(error="Not authenticated").model_dump(),
        )

    user_id = store.get_user_id_from_session(db, sa_session)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse(error="Not authenticated").model_dump(),
        )

    user = store.get_user(db, user_id)
    if not user:
        store.destroy_session(db, sa_session)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse(error="Not authenticated").model_dump(),
        )

    return db, user_id, user


def user_response(user: store.User) -> UserResponse:
    return UserResponse(**user.to_dict())
