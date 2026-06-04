"""Data access facade: PostgreSQL when DATABASE_URL/POSTGRES_URL is set, else in-memory."""

from sqlalchemy.orm import Session

from app.config import settings
from app.services import db_store, memory_store

User = memory_store.User
Contact = memory_store.Contact
Emergency = memory_store.Emergency
AdminEmergency = memory_store.AdminEmergency
AdminUser = memory_store.AdminUser


def create_session(db: Session | None, user_id: str) -> str:
    if db is not None:
        return db_store.create_session(db, user_id)
    return memory_store.create_session(user_id)


def get_user_id_from_session(db: Session | None, session_id: str) -> str | None:
    if db is not None:
        return db_store.get_user_id_from_session(db, session_id)
    return memory_store.get_user_id_from_session(session_id)


def destroy_session(db: Session | None, session_id: str) -> None:
    if db is not None:
        db_store.destroy_session(db, session_id)
    else:
        memory_store.destroy_session(session_id)


def register_user(db: Session | None, name: str, email: str) -> User:
    if db is not None:
        return db_store.register_user(db, name, email)
    return memory_store.register_user(name, email)


def login_user(db: Session | None, email: str) -> User | None:
    if db is not None:
        return db_store.login_user(db, email)
    return memory_store.login_user(email)


def get_user(db: Session | None, user_id: str) -> User | None:
    if db is not None:
        return db_store.get_user(db, user_id)
    return memory_store.get_user(user_id)


def update_user(
    db: Session | None,
    user_id: str,
    *,
    name: str | None = None,
    emergency_phrase: str | None = None,
    emergency_phrase_set: bool = False,
) -> User | None:
    if db is not None:
        return db_store.update_user(
            db,
            user_id,
            name=name,
            emergency_phrase=emergency_phrase,
            emergency_phrase_set=emergency_phrase_set,
        )
    return memory_store.update_user(
        user_id,
        name=name,
        emergency_phrase=emergency_phrase,
        emergency_phrase_set=emergency_phrase_set,
    )


def list_contacts(db: Session | None, user_id: str) -> list[Contact]:
    if db is not None:
        return db_store.list_contacts(db, user_id)
    return memory_store.list_contacts(user_id)


def add_contact(db: Session | None, user_id: str, name: str, phone: str, priority: int) -> Contact:
    if db is not None:
        return db_store.add_contact(db, user_id, name, phone, priority)
    return memory_store.add_contact(user_id, name, phone, priority)


def update_contact(
    db: Session | None,
    user_id: str,
    contact_id: str,
    *,
    priority: int | None = None,
    name: str | None = None,
    phone: str | None = None,
) -> Contact | None:
    if db is not None:
        return db_store.update_contact(
            db, user_id, contact_id, priority=priority, name=name, phone=phone
        )
    return memory_store.update_contact(
        user_id, contact_id, priority=priority, name=name, phone=phone
    )


def delete_contact(db: Session | None, user_id: str, contact_id: str) -> bool:
    if db is not None:
        return db_store.delete_contact(db, user_id, contact_id)
    return memory_store.delete_contact(user_id, contact_id)


def get_active_emergency(db: Session | None, user_id: str) -> Emergency | None:
    if db is not None:
        return db_store.get_active_emergency(db, user_id)
    return memory_store.get_active_emergency(user_id)


def create_emergency(db: Session | None, user_id: str) -> Emergency:
    if db is not None:
        return db_store.create_emergency(db, user_id)
    return memory_store.create_emergency(user_id)


def update_emergency(
    db: Session | None,
    user_id: str,
    emergency_id: str,
    *,
    status: str | None = None,
) -> Emergency | None:
    if db is not None:
        return db_store.update_emergency(db, user_id, emergency_id, status=status)
    return memory_store.update_emergency(user_id, emergency_id, status=status)


def list_admin_emergencies(db: Session | None) -> list[AdminEmergency]:
    if db is not None:
        return db_store.list_admin_emergencies(db)
    return memory_store.list_admin_emergencies()


def list_admin_users(db: Session | None) -> list[AdminUser]:
    if db is not None:
        return db_store.list_admin_users(db)
    return memory_store.list_admin_users()


def set_user_suspended(db: Session | None, user_id: str, suspended: bool) -> User | None:
    if db is not None:
        return db_store.set_user_suspended(db, user_id, suspended)
    return memory_store.set_user_suspended(user_id, suspended)


def admin_resolve_emergency(db: Session | None, emergency_id: str) -> Emergency | None:
    if db is not None:
        return db_store.admin_resolve_emergency(db, emergency_id)
    return memory_store.admin_resolve_emergency(emergency_id)


def storage_mode() -> str:
    return "postgres" if settings.uses_database else "memory"
