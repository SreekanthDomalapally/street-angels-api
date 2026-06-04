from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.db.database import DbSession
from app.dependencies import clear_session_cookie, require_user, set_session_cookie, user_response
from app.schemas.user import AuthRegister, ErrorResponse, LoginRequest, UserResponse
from app.services import store

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse)
def register(body: AuthRegister, response: Response, db: DbSession) -> UserResponse:
    if not body.name.strip() or not str(body.email).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(error="Name and email required").model_dump(),
        )

    user = store.register_user(db, body.name, str(body.email))
    session_id = store.create_session(db, user.id)
    set_session_cookie(response, session_id)
    return user_response(user)


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, response: Response, db: DbSession) -> UserResponse:
    email = str(body.email).strip()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(error="Email required").model_dump(),
        )

    name = body.name or email.split("@")[0] or "User"
    user = store.login_user(db, email)
    if not user:
        user = store.register_user(db, name, email)

    session_id = store.create_session(db, user.id)
    set_session_cookie(response, session_id)
    return user_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: DbSession,
    sa_session: Annotated[str | None, Cookie(alias="sa_session")] = None,
) -> None:
    if sa_session:
        store.destroy_session(db, sa_session)
    clear_session_cookie(response)


@router.get("/me", response_model=UserResponse)
def me(
    auth: Annotated[tuple, Depends(require_user)],
) -> UserResponse:
    _, _, user = auth
    return user_response(user)
