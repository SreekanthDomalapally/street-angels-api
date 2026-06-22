from fastapi import APIRouter

from app.api.v1 import alerts, auth, contacts, donations, groups, invites, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(contacts.router)
api_router.include_router(invites.router)
api_router.include_router(groups.router)
api_router.include_router(alerts.router)
api_router.include_router(donations.router)
