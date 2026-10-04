"""Team routes."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import ContainerDep, OrgDep
from app.schemas.organization import MemberWithUser, Team, TeamCreate, TeamUpdate

router = APIRouter(tags=["teams"])


@router.get("/organizations/{organization_id}/teams", response_model=list[Team])
async def list_teams(container: ContainerDep, ctx: OrgDep) -> list[Team]:
    return await container.teams.list(ctx.organization.id)


@router.post(
    "/organizations/{organization_id}/teams", response_model=Team, status_code=status.HTTP_201_CREATED
)
async def create_team(container: ContainerDep, ctx: OrgDep, payload: TeamCreate) -> Team:
    return await container.teams.create(ctx.principal, ctx.organization.id, payload)


@router.get("/organizations/{organization_id}/teams/{team_id}", response_model=Team)
async def get_team(container: ContainerDep, ctx: OrgDep, team_id: str) -> Team:
    return await container.teams.get(ctx.organization.id, team_id)


@router.get(
    "/organizations/{organization_id}/teams/{team_id}/members",
    response_model=list[MemberWithUser],
)
async def team_members(
    container: ContainerDep, ctx: OrgDep, team_id: str
) -> list[MemberWithUser]:
    return await container.teams.members(ctx.organization.id, team_id)


@router.patch("/organizations/{organization_id}/teams/{team_id}", response_model=Team)
async def update_team(
    container: ContainerDep, ctx: OrgDep, team_id: str, patch: TeamUpdate
) -> Team:
    return await container.teams.update(ctx.principal, ctx.organization.id, team_id, patch)


@router.delete(
    "/organizations/{organization_id}/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_team(container: ContainerDep, ctx: OrgDep, team_id: str) -> None:
    await container.teams.delete(ctx.principal, ctx.organization.id, team_id)
