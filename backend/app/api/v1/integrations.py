"""Integration routes: catalogue, connect, OAuth, scopes, disconnect."""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from fastapi.responses import RedirectResponse

from app.api.deps import ContainerDep, OrgDep
from app.core.errors import PermissionDeniedError
from app.core.logging import get_logger
from app.schemas.enums import IntegrationProvider, OrgRole
from app.schemas.integration import (
    IntegrationCatalogEntry,
    IntegrationConnectToken,
    IntegrationPublic,
    IntegrationScopesUpdate,
    OAuthStartResponse,
)

logger = get_logger(__name__)

router = APIRouter(tags=["integrations"])
callback_router = APIRouter(tags=["integrations"])

_ADMINS = {OrgRole.OWNER, OrgRole.ADMIN}


def _require_admin(role: OrgRole | None) -> None:
    if role not in _ADMINS:
        raise PermissionDeniedError("Only organization owners and admins can manage integrations.")


@router.get(
    "/organizations/{organization_id}/integrations", response_model=list[IntegrationPublic]
)
async def list_integrations(container: ContainerDep, ctx: OrgDep) -> list[IntegrationPublic]:
    return await container.integrations.list(ctx.organization.id)


@router.get(
    "/organizations/{organization_id}/integrations/catalogue",
    response_model=list[IntegrationCatalogEntry],
)
async def integration_catalogue(
    container: ContainerDep, ctx: OrgDep
) -> list[IntegrationCatalogEntry]:
    return await container.integrations.catalogue()


@router.post(
    "/organizations/{organization_id}/integrations/token",
    response_model=IntegrationPublic,
    status_code=status.HTTP_201_CREATED,
)
async def connect_with_token(
    container: ContainerDep, ctx: OrgDep, payload: IntegrationConnectToken
) -> IntegrationPublic:
    return await container.integrations.connect_token(ctx.principal, ctx.organization.id, payload)


@router.get(
    "/organizations/{organization_id}/integrations/{provider}/oauth/start",
    response_model=OAuthStartResponse,
)
async def oauth_start(
    container: ContainerDep,
    ctx: OrgDep,
    provider: IntegrationProvider,
    redirect_uri: str | None = Query(default=None),
) -> OAuthStartResponse:
    _require_admin(ctx.member.role)
    target = redirect_uri or f"{container.settings.oauth_redirect_base_url}/api/v1/integrations/oauth/{provider.value}/callback"
    return await container.integrations.oauth_start(ctx.organization.id, provider, target)


@router.patch(
    "/organizations/{organization_id}/integrations/{integration_id}",
    response_model=IntegrationPublic,
)
async def update_integration_scopes(
    container: ContainerDep,
    ctx: OrgDep,
    integration_id: str,
    payload: IntegrationScopesUpdate,
) -> IntegrationPublic:
    return await container.integrations.update_scopes(
        ctx.principal, ctx.organization.id, integration_id, payload
    )


@router.delete(
    "/organizations/{organization_id}/integrations/{integration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def disconnect_integration(
    container: ContainerDep, ctx: OrgDep, integration_id: str
) -> None:
    await container.integrations.disconnect(ctx.principal, ctx.organization.id, integration_id)


@router.post(
    "/organizations/{organization_id}/integrations/{integration_id}/refresh",
    response_model=IntegrationPublic,
)
async def refresh_integration(
    container: ContainerDep, ctx: OrgDep, integration_id: str
) -> IntegrationPublic:
    return await container.integrations.refresh_resources(
        ctx.principal, ctx.organization.id, integration_id
    )


@callback_router.get("/integrations/oauth/{provider}/callback", include_in_schema=False)
async def oauth_callback(
    container: ContainerDep, provider: IntegrationProvider, code: str, state: str
) -> RedirectResponse:
    from app.integrations.oauth import verify_state

    state_data = verify_state(state, container.settings.dev_auth_secret)
    organization_id = str(state_data.get("org") or state_data.get("organization_id") or "")
    integration = await container.integrations.connect_oauth_callback(
        organization_id, provider, code, state
    )
    target = (
        f"{container.settings.frontend_url}/integrations"
        f"?connected={provider.value}&org={integration.organization_id}"
    )
    return RedirectResponse(target, status_code=status.HTTP_302_FOUND)
