"""FastAPI dependencies.

Identity comes from the bearer token only. Organization membership is resolved from the
store on every request — the frontend cannot assert either.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request

from app.container import Container
from app.core.errors import UnauthenticatedError
from app.core.logging import set_request_context
from app.runtime.permissions.engine import AccessContext
from app.schemas.auth import Principal
from app.schemas.organization import Member, Organization


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


def _parse_bearer(authorization: str | None) -> str:
    if not authorization:
        raise UnauthenticatedError("Sign in to continue.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthenticatedError("Invalid authorization header.")
    return token.strip()


async def get_principal(
    container: ContainerDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    token = _parse_bearer(authorization)
    principal = await container.auth.principal_from_token(token)
    set_request_context(user_id=principal.user_id, organization_id=principal.organization_id)
    return principal


PrincipalDep = Annotated[Principal, Depends(get_principal)]


@dataclass
class OrgContext:
    organization: Organization
    member: Member
    access: AccessContext
    principal: Principal


async def get_org_context(
    organization_id: str,
    container: ContainerDep,
    principal: PrincipalDep,
) -> OrgContext:
    organization = await container.organizations.get(organization_id)
    member = await container.organizations.require_membership(organization_id, principal.user_id)
    set_request_context(organization_id=organization_id)
    access = AccessContext(
        user_id=principal.user_id,
        org_role=member.role,
        team_ids=tuple(member.team_ids),
        settings=organization.settings,
    )
    return OrgContext(
        organization=organization, member=member, access=access, principal=principal
    )


OrgDep = Annotated[OrgContext, Depends(get_org_context)]
