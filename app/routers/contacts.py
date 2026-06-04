from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import require_user
from app.schemas.contact import ContactCreate, ContactResponse, ContactUpdate, DeleteResponse
from app.schemas.user import ErrorResponse
from app.services import store

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _contact_response(contact: store.Contact) -> ContactResponse:
    return ContactResponse(**contact.to_dict())


@router.get("", response_model=list[ContactResponse])
def list_contacts(
    auth: Annotated[tuple, Depends(require_user)],
) -> list[ContactResponse]:
    db, user_id, _ = auth
    return [_contact_response(c) for c in store.list_contacts(db, user_id)]


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
def create_contact(
    body: ContactCreate,
    auth: Annotated[tuple, Depends(require_user)],
) -> ContactResponse:
    db, user_id, _ = auth
    if not body.name.strip() or not body.phone.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(error="Name and phone required").model_dump(),
        )

    priority = (
        body.priority
        if body.priority is not None
        else len(store.list_contacts(db, user_id)) + 1
    )
    contact = store.add_contact(db, user_id, body.name, body.phone, priority)
    return _contact_response(contact)


@router.patch("/{contact_id}", response_model=ContactResponse)
def patch_contact(
    contact_id: str,
    body: ContactUpdate,
    auth: Annotated[tuple, Depends(require_user)],
) -> ContactResponse:
    db, user_id, _ = auth
    contact = store.update_contact(
        db,
        user_id,
        contact_id,
        priority=body.priority,
        name=body.name,
        phone=body.phone,
    )
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(error="Contact not found").model_dump(),
        )
    return _contact_response(contact)


@router.delete("/{contact_id}", response_model=DeleteResponse)
def remove_contact(
    contact_id: str,
    auth: Annotated[tuple, Depends(require_user)],
) -> DeleteResponse:
    db, user_id, _ = auth
    if not store.delete_contact(db, user_id, contact_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(error="Contact not found").model_dump(),
        )
    return DeleteResponse()
