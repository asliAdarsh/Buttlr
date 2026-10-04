"""Model provider routes and the runtime model catalogue."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import ContainerDep, OrgDep
from app.schemas.models import ModelProviderEntry, ModelProviderUpdate

router = APIRouter(tags=["models"])


@router.get("/organizations/{organization_id}/models", response_model=list[ModelProviderEntry])
async def list_model_providers(
    container: ContainerDep, ctx: OrgDep
) -> list[ModelProviderEntry]:
    """Every model provider this workspace can choose, and where its credentials come from."""
    return await container.models.entries(ctx.organization.id)


@router.get(
    "/organizations/{organization_id}/models/available", response_model=list[ModelProviderEntry]
)
async def available_model_providers(
    container: ContainerDep, ctx: OrgDep
) -> list[ModelProviderEntry]:
    """Only the providers that can answer right now — what the pickers offer."""
    return await container.models.selectable(ctx.organization.id)


@router.put(
    "/organizations/{organization_id}/models/{provider}", response_model=ModelProviderEntry
)
async def set_model_provider(
    container: ContainerDep,
    ctx: OrgDep,
    provider: str,
    payload: ModelProviderUpdate,
) -> ModelProviderEntry:
    """Configure a provider for this workspace: an API key, a local endpoint, or both."""
    return await container.models.set_provider(ctx.principal, ctx.organization.id, provider, payload)


@router.delete(
    "/organizations/{organization_id}/models/{provider}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def clear_model_provider(
    container: ContainerDep, ctx: OrgDep, provider: str
) -> None:
    await container.models.clear_provider(ctx.principal, ctx.organization.id, provider)
