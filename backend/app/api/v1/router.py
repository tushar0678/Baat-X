from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai,
    assistant,
    auth,
    customers,
    followups,
    leads,
    reports,
    whatsapp,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(ai.router)
api_router.include_router(customers.router)
api_router.include_router(leads.router)
api_router.include_router(followups.router)
api_router.include_router(reports.router)
api_router.include_router(whatsapp.router)
api_router.include_router(assistant.router)
