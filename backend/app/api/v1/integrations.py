"""Integration routes: catalogue, connect, OAuth, scopes, disconnect.

Connections are made here, in the application. Nothing about a provider account is read from
the deployment's environment: each person may connect their own account, and an owner or
admin may additionally connect one shared account for the workspace.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from fastapi.responses import RedirectResponse

from app.api.deps import ContainerDep, OrgDep
from app.core.errors import PermissionDeniedError
from app.core.logging import get_logger
from app.schemas.enums import IntegrationProvider, IntegrationScope, OrgRole
from app.schemas.integration import (
    IntegrationCatalogEntry,
    IntegrationConnectToken,
    IntegrationPublic,
    IntegrationScopesUpdate,
    OAuthClientPublic,
    OAuthClientUpdate,
    OAuthStartResponse,
)

logger = get_logger(__name__)

router = APIRouter(tags=["integrations"])
callback_router = APIRouter(tags=["integrations"])

_ADMINS = {OrgRole.OWNER, OrgRole.ADMIN}


def _is_admin(role: OrgRole | None) -> bool:
    return role in _ADMINS


@router.get(
    "/organizations/{organization_id}/integrations", response_model=list[IntegrationPublic]
)
async def list_integrations(container: ContainerDep, ctx: OrgDep) -> list[IntegrationPublic]:
    """The workspace's shared connections plus this person's own."""
    return await container.integrations.list(
        ctx.organization.id,
        viewer_id=ctx.principal.user_id,
        is_admin=_is_admin(ctx.member.role),
    )


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
    """Connect GitHub or Jira with a token. Any member may connect their own account."""
    return await container.integrations.connect_token(ctx.principal, ctx.organization.id, payload)


@router.get(
    "/organizations/{organization_id}/integrations/oauth-clients",
    response_model=list[OAuthClientPublic],
)
async def oauth_clients(container: ContainerDep, ctx: OrgDep) -> list[OAuthClientPublic]:
    """Which OAuth apps are available for this workspace; never returns a secret."""
    return await container.integrations.oauth_clients(ctx.organization.id)


@router.put(
    "/organizations/{organization_id}/integrations/oauth-clients/{provider}",
    response_model=OAuthClientPublic,
)
async def set_oauth_client(
    container: ContainerDep,
    ctx: OrgDep,
    provider: IntegrationProvider,
    payload: OAuthClientUpdate,
) -> OAuthClientPublic:
    """Register the workspace's own OAuth app so connections need no deployment secret."""
    return await container.integrations.set_oauth_client(
        ctx.principal, ctx.organization.id, provider, payload
    )


@router.delete(
    "/organizations/{organization_id}/integrations/oauth-clients/{provider}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def clear_oauth_client(
    container: ContainerDep, ctx: OrgDep, provider: IntegrationProvider
) -> None:
    await container.integrations.clear_oauth_client(ctx.principal, ctx.organization.id, provider)


@router.get(
    "/organizations/{organization_id}/integrations/{provider}/oauth/start",
    response_model=OAuthStartResponse,
)
async def oauth_start(
    container: ContainerDep,
    ctx: OrgDep,
    provider: IntegrationProvider,
    scope: IntegrationScope = Query(default=IntegrationScope.PERSONAL),
    redirect_uri: str | None = Query(default=None),
) -> OAuthStartResponse:
    """Begin an OAuth connection. Members connect their own account; admins may share one."""
    if scope is IntegrationScope.ORGANIZATION and not _is_admin(ctx.member.role):
        raise PermissionDeniedError(
            "Only organization owners and admins can connect a shared account. "
            "Connect it for yourself instead."
        )
    target = redirect_uri or container.integrations.callback_url(provider)
    return await container.integrations.oauth_start(
        ctx.organization.id,
        provider,
        target,
        user_id=ctx.principal.user_id,
        scope=scope,
    )


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
    organization_id = str(state_data.get("org") or "")
    integration = await container.integrations.connect_oauth_callback(
        organization_id, provider, code, state
    )
    target = (
        f"{container.settings.frontend_url}/integrations"
        f"?connected={provider.value}&org={integration.organization_id}"
    )
    return RedirectResponse(target, status_code=status.HTTP_302_FOUND)
