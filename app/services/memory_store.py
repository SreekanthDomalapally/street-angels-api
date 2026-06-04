import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

DEFAULT_CONTACTS = [
    {"name": "Sarah", "phone": "+1 555 010 0001", "priority": 1},
    {"name": "James", "phone": "+1 555 010 0002", "priority": 2},
    {"name": "Mum", "phone": "+1 555 010 0003", "priority": 3},
]


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class User:
    id: str
    name: str
    email: str
    emergency_phrase: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "emergencyPhrase": self.emergency_phrase,
        }


@dataclass
class Contact:
    id: str
    user_id: str
    name: str
    phone: str
    priority: int

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "userId": self.user_id,
            "name": self.name,
            "phone": self.phone,
            "priority": self.priority,
        }


@dataclass
class Emergency:
    id: str
    user_id: str
    status: str
    started_at: str
    lat: float
    lng: float

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "userId": self.user_id,
            "status": self.status,
            "startedAt": self.started_at,
            "lat": self.lat,
            "lng": self.lng,
        }


@dataclass
class _Store:
    users: dict[str, User] = field(default_factory=dict)
    sessions: dict[str, str] = field(default_factory=dict)
    contacts: dict[str, Contact] = field(default_factory=dict)
    emergencies: dict[str, Emergency] = field(default_factory=dict)
    email_to_user_id: dict[str, str] = field(default_factory=dict)


_store = _Store()


def _get() -> _Store:
    return _store


def create_session(user_id: str) -> str:
    session_id = _new_id()
    _get().sessions[session_id] = user_id
    return session_id


def get_user_id_from_session(session_id: str) -> str | None:
    return _get().sessions.get(session_id)


def destroy_session(session_id: str) -> None:
    _get().sessions.pop(session_id, None)


def _seed_contacts(user_id: str) -> None:
    store = _get()
    if any(c.user_id == user_id for c in store.contacts.values()):
        return
    for c in DEFAULT_CONTACTS:
        contact = Contact(
            id=_new_id(),
            user_id=user_id,
            name=c["name"],
            phone=c["phone"],
            priority=c["priority"],
        )
        store.contacts[contact.id] = contact


def register_user(name: str, email: str) -> User:
    store = _get()
    normalized = email.lower().strip()
    existing_id = store.email_to_user_id.get(normalized)
    if existing_id and existing_id in store.users:
        return store.users[existing_id]

    user = User(id=_new_id(), name=name.strip(), email=normalized)
    store.users[user.id] = user
    store.email_to_user_id[normalized] = user.id
    _seed_contacts(user.id)
    return user


def login_user(email: str) -> User | None:
    store = _get()
    normalized = email.lower().strip()
    user_id = store.email_to_user_id.get(normalized)
    if not user_id:
        return None
    return store.users.get(user_id)


def get_user(user_id: str) -> User | None:
    return _get().users.get(user_id)


def update_user(
    user_id: str,
    *,
    name: str | None = None,
    emergency_phrase: str | None = None,
    emergency_phrase_set: bool = False,
) -> User | None:
    user = _get().users.get(user_id)
    if not user:
        return None
    if name is not None:
        user.name = name.strip()
    if emergency_phrase_set:
        user.emergency_phrase = emergency_phrase.strip() if emergency_phrase else None
    return user


def list_contacts(user_id: str) -> list[Contact]:
    return sorted(
        (c for c in _get().contacts.values() if c.user_id == user_id),
        key=lambda c: c.priority,
    )


def add_contact(user_id: str, name: str, phone: str, priority: int) -> Contact:
    contact = Contact(
        id=_new_id(),
        user_id=user_id,
        name=name.strip(),
        phone=phone.strip(),
        priority=priority,
    )
    _get().contacts[contact.id] = contact
    return contact


def update_contact(
    user_id: str,
    contact_id: str,
    *,
    priority: int | None = None,
    name: str | None = None,
    phone: str | None = None,
) -> Contact | None:
    contact = _get().contacts.get(contact_id)
    if not contact or contact.user_id != user_id:
        return None
    if priority is not None:
        contact.priority = priority
    if name is not None:
        contact.name = name.strip()
    if phone is not None:
        contact.phone = phone.strip()
    return contact


def delete_contact(user_id: str, contact_id: str) -> bool:
    contact = _get().contacts.get(contact_id)
    if not contact or contact.user_id != user_id:
        return False
    del _get().contacts[contact_id]
    return True


def get_active_emergency(user_id: str) -> Emergency | None:
    for e in _get().emergencies.values():
        if e.user_id == user_id and e.status == "active":
            return e
    return None


def create_emergency(user_id: str) -> Emergency:
    existing = get_active_emergency(user_id)
    if existing:
        return existing

    emergency = Emergency(
        id=_new_id(),
        user_id=user_id,
        status="active",
        started_at=datetime.now(timezone.utc).isoformat(),
        lat=51.507 + (random.random() - 0.5) * 0.02,
        lng=-0.127 + (random.random() - 0.5) * 0.02,
    )
    _get().emergencies[emergency.id] = emergency
    return emergency


def update_emergency(
    user_id: str,
    emergency_id: str,
    *,
    status: str | None = None,
) -> Emergency | None:
    emergency = _get().emergencies.get(emergency_id)
    if not emergency or emergency.user_id != user_id:
        return None
    if status:
        emergency.status = status
    return emergency
