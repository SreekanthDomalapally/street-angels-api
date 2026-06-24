from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    analytics,
    auth,
    contacts,
    donations,
    emergency_types,
    groups,
    invites,
    skills,
    trips,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(contacts.router)
api_router.include_router(invites.router)
api_router.include_router(groups.router)
api_router.include_router(alerts.router)
api_router.include_router(analytics.router)
api_router.include_router(emergency_types.router)
api_router.include_router(skills.router)
api_router.include_router(trips.router)
api_router.include_router(donations.router)
