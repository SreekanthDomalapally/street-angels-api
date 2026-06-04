"""Session-cookie API used by street-angels-ui (prefix /api)."""

from fastapi import APIRouter

from app.routers import admin, auth, contacts, emergencies, users

legacy_api_router = APIRouter()
legacy_api_router.include_router(auth.router)
legacy_api_router.include_router(users.router)
legacy_api_router.include_router(contacts.router)
legacy_api_router.include_router(emergencies.router)
legacy_api_router.include_router(admin.router)
