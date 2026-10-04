"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    activity,
    analytics,
    approvals,
    auth,
    buttlrs,
    dev,
    executions,
    health,
    integrations,
    organizations,
    teams,
    tools,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(teams.router)
api_router.include_router(buttlrs.router)
api_router.include_router(executions.router)
api_router.include_router(approvals.router)
api_router.include_router(integrations.router)
api_router.include_router(integrations.callback_router)
api_router.include_router(activity.router)
api_router.include_router(analytics.router)
api_router.include_router(tools.router)
api_router.include_router(dev.router)

__all__ = ["api_router"]
