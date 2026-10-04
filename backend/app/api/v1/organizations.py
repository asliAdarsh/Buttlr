"""Organization and membership routes."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import ContainerDep, OrgDep, PrincipalDep
from app.schemas.organization import (
    MemberInvite,
    MemberUpdate,
    MemberWithUser,
    Organization,
    OrganizationCreate,
    OrganizationUpdate,
    OrgSummary,
    UserUpdate,
)

router = APIRouter(tags=["organizations"])


@router.get("/organizations", response_model=list[OrgSummary])
async def list_organizations(
    container: ContainerDep, principal: PrincipalDep
) -> list[OrgSummary]:
    return await container.organizations.list_for_user(principal.user_id)


@router.post("/organizations", response_model=Organization, status_code=status.HTTP_201_CREATED)
async def create_organization(
    container: ContainerDep, principal: PrincipalDep, payload: OrganizationCreate
) -> Organization:
    organization = await container.organizations.create(principal, payload)
    await container.auth.update_user(
        principal.user_id, UserUpdate(default_organization_id=organization.id)
    )
    return organization


@router.get("/organizations/{organization_id}", response_model=Organization)
async def get_organization(ctx: OrgDep) -> Organization:
    return ctx.organization


@router.patch("/organizations/{organization_id}", response_model=Organization)
async def update_organization(
    container: ContainerDep, ctx: OrgDep, patch: OrganizationUpdate
) -> Organization:
    return await container.organizations.update(ctx.principal, ctx.organization.id, patch)


@router.get("/organizations/{organization_id}/members", response_model=list[MemberWithUser])
async def list_members(container: ContainerDep, ctx: OrgDep) -> list[MemberWithUser]:
    return await container.organizations.members(ctx.organization.id)


@router.post(
    "/organizations/{organization_id}/members",
    response_model=MemberWithUser,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    container: ContainerDep, ctx: OrgDep, payload: MemberInvite
) -> MemberWithUser:
    return await container.organizations.invite(ctx.principal, ctx.organization.id, payload)


@router.patch("/organizations/{organization_id}/members/{user_id}", response_model=MemberWithUser)
async def update_member(
    container: ContainerDep, ctx: OrgDep, user_id: str, patch: MemberUpdate
) -> MemberWithUser:
    return await container.organizations.update_member(ctx.principal, ctx.organization.id, user_id, patch)


@router.delete("/organizations/{organization_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(container: ContainerDep, ctx: OrgDep, user_id: str) -> None:
    await container.organizations.remove_member(ctx.principal, ctx.organization.id, user_id)
