"""Analytics and dashboard routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep, OrgDep
from app.schemas.activity import AnalyticsOverview, DashboardOverview

router = APIRouter(tags=["analytics"])


@router.get(
    "/organizations/{organization_id}/analytics/overview", response_model=AnalyticsOverview
)
async def analytics_overview(
    container: ContainerDep,
    ctx: OrgDep,
    days: int = Query(default=30, ge=1, le=180),
) -> AnalyticsOverview:
    return await container.analytics.overview(ctx.organization.id, days=days)


@router.get("/organizations/{organization_id}/dashboard", response_model=DashboardOverview)
async def dashboard(container: ContainerDep, ctx: OrgDep) -> DashboardOverview:
    return await container.analytics.dashboard(ctx.principal, ctx.organization.id)


__all__ = ["router"]
