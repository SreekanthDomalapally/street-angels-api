import random
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ContactRow, EmergencyRow, SessionRow, UserRow
from app.services.memory_store import DEFAULT_CONTACTS, Contact, Emergency, User


def _new_id() -> str:
    return str(uuid.uuid4())


def _user_from_row(row: UserRow) -> User:
    return User(
        id=row.id,
        name=row.name,
        email=row.email,
        emergency_phrase=row.emergency_phrase,
    )


def _contact_from_row(row: ContactRow) -> Contact:
    return Contact(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        phone=row.phone,
        priority=row.priority,
    )


def _emergency_from_row(row: EmergencyRow) -> Emergency:
    started = row.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return Emergency(
        id=row.id,
        user_id=row.user_id,
        status=row.status,
        started_at=started.isoformat(),
        lat=row.lat,
        lng=row.lng,
    )


def _seed_contacts(db: Session, user_id: str) -> None:
    existing = db.scalar(
        select(ContactRow.id).where(ContactRow.user_id == user_id).limit(1)
    )
    if existing:
        return
    for c in DEFAULT_CONTACTS:
        db.add(
            ContactRow(
                id=_new_id(),
                user_id=user_id,
                name=c["name"],
                phone=c["phone"],
                priority=c["priority"],
            )
        )
    db.flush()


def create_session(db: Session, user_id: str) -> str:
    session_id = _new_id()
    db.add(SessionRow(id=session_id, user_id=user_id))
    db.flush()
    return session_id


def get_user_id_from_session(db: Session, session_id: str) -> str | None:
    row = db.get(SessionRow, session_id)
    return row.user_id if row else None


def destroy_session(db: Session, session_id: str) -> None:
    row = db.get(SessionRow, session_id)
    if row:
        db.delete(row)


def register_user(db: Session, name: str, email: str) -> User:
    normalized = email.lower().strip()
    row = db.scalar(select(UserRow).where(UserRow.email == normalized))
    if row:
        return _user_from_row(row)

    user_row = UserRow(
        id=_new_id(),
        name=name.strip(),
        email=normalized,
        emergency_phrase=None,
    )
    db.add(user_row)
    db.flush()
    _seed_contacts(db, user_row.id)
    return _user_from_row(user_row)


def login_user(db: Session, email: str) -> User | None:
    normalized = email.lower().strip()
    row = db.scalar(select(UserRow).where(UserRow.email == normalized))
    return _user_from_row(row) if row else None


def get_user(db: Session, user_id: str) -> User | None:
    row = db.get(UserRow, user_id)
    return _user_from_row(row) if row else None


def update_user(
    db: Session,
    user_id: str,
    *,
    name: str | None = None,
    emergency_phrase: str | None = None,
    emergency_phrase_set: bool = False,
) -> User | None:
    row = db.get(UserRow, user_id)
    if not row:
        return None
    if name is not None:
        row.name = name.strip()
    if emergency_phrase_set:
        row.emergency_phrase = emergency_phrase.strip() if emergency_phrase else None
    db.flush()
    return _user_from_row(row)


def list_contacts(db: Session, user_id: str) -> list[Contact]:
    rows = db.scalars(
        select(ContactRow).where(ContactRow.user_id == user_id).order_by(ContactRow.priority)
    ).all()
    return [_contact_from_row(r) for r in rows]


def add_contact(db: Session, user_id: str, name: str, phone: str, priority: int) -> Contact:
    row = ContactRow(
        id=_new_id(),
        user_id=user_id,
        name=name.strip(),
        phone=phone.strip(),
        priority=priority,
    )
    db.add(row)
    db.flush()
    return _contact_from_row(row)


def update_contact(
    db: Session,
    user_id: str,
    contact_id: str,
    *,
    priority: int | None = None,
    name: str | None = None,
    phone: str | None = None,
) -> Contact | None:
    row = db.get(ContactRow, contact_id)
    if not row or row.user_id != user_id:
        return None
    if priority is not None:
        row.priority = priority
    if name is not None:
        row.name = name.strip()
    if phone is not None:
        row.phone = phone.strip()
    db.flush()
    return _contact_from_row(row)


def delete_contact(db: Session, user_id: str, contact_id: str) -> bool:
    row = db.get(ContactRow, contact_id)
    if not row or row.user_id != user_id:
        return False
    db.delete(row)
    return True


def get_active_emergency(db: Session, user_id: str) -> Emergency | None:
    row = db.scalar(
        select(EmergencyRow)
        .where(EmergencyRow.user_id == user_id, EmergencyRow.status == "active")
        .limit(1)
    )
    return _emergency_from_row(row) if row else None


def create_emergency(db: Session, user_id: str) -> Emergency:
    existing = get_active_emergency(db, user_id)
    if existing:
        return existing

    row = EmergencyRow(
        id=_new_id(),
        user_id=user_id,
        status="active",
        started_at=datetime.now(timezone.utc),
        lat=51.507 + (random.random() - 0.5) * 0.02,
        lng=-0.127 + (random.random() - 0.5) * 0.02,
    )
    db.add(row)
    db.flush()
    return _emergency_from_row(row)


def update_emergency(
    db: Session,
    user_id: str,
    emergency_id: str,
    *,
    status: str | None = None,
) -> Emergency | None:
    row = db.get(EmergencyRow, emergency_id)
    if not row or row.user_id != user_id:
        return None
    if status:
        row.status = status
    db.flush()
    return _emergency_from_row(row)
