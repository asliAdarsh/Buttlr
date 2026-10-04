"""Integrations and their public projection.

Credentials live in the stored document only; ``to_public`` is the only shape that ever
reaches an HTTP response.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import DomainModel, utcnow
from app.schemas.enums import IntegrationProvider, IntegrationScope, IntegrationStatus


class IntegrationResource(DomainModel):
    """A connectable thing inside a provider (repository, project, label, folder…)."""

    id: str
    name: str
    kind: str = "resource"
    selected: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)


class Integration(DomainModel):
    id: str
    organization_id: str
    provider: IntegrationProvider
    display_name: str
    scope: IntegrationScope = IntegrationScope.ORGANIZATION
    owner_id: str | None = None
    owner_name: str | None = None
    status: IntegrationStatus = IntegrationStatus.CONNECTED
    account: str | None = None
    scopes: list[str] = Field(default_factory=list)
    resources: list[IntegrationResource] = Field(default_factory=list)
    credentials: dict[str, Any] = Field(default_factory=dict, exclude=True, repr=False)
    error: str | None = None
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    last_used_at: datetime | None = None

    def to_public(self) -> IntegrationPublic:
        return IntegrationPublic(
            id=self.id,
            organization_id=self.organization_id,
            provider=self.provider,
            display_name=self.display_name,
            scope=self.scope,
            owner_id=self.owner_id,
            owner_name=self.owner_name,
            status=self.status,
            account=self.account,
            scopes=self.scopes,
            resources=self.resources,
            error=self.error,
            created_at=self.created_at,
            updated_at=self.updated_at,
            last_used_at=self.last_used_at,
        )


class IntegrationPublic(DomainModel):
    id: str
    organization_id: str
    provider: IntegrationProvider
    display_name: str
    scope: IntegrationScope = IntegrationScope.ORGANIZATION
    owner_id: str | None = None
    owner_name: str | None = None
    status: IntegrationStatus
    account: str | None = None
    scopes: list[str] = Field(default_factory=list)
    resources: list[IntegrationResource] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None


class IntegrationConnectToken(DomainModel):
    """Token/API-key based connection (GitHub PAT, Jira API token)."""

    provider: IntegrationProvider
    token: str = Field(min_length=8)
    scope: IntegrationScope = IntegrationScope.PERSONAL
    account: str | None = None
    base_url: str | None = None
    email: str | None = None
    label: str | None = None


class OAuthClientUpdate(DomainModel):
    """A workspace's own OAuth application (so no deployment secret is needed)."""

    client_id: str = Field(min_length=8, max_length=200)
    client_secret: str | None = Field(default=None, max_length=400)


class OAuthClientPublic(DomainModel):
    """Never carries the secret — only whether one is stored."""

    provider: IntegrationProvider
    configured: bool = False
    client_id: str | None = None
    masked_client_id: str | None = None
    has_secret: bool = False
    source: str | None = None
    redirect_uri: str | None = None


class IntegrationScopesUpdate(DomainModel):
    resource_ids: list[str] = Field(default_factory=list)


class IntegrationCatalogEntry(DomainModel):
    provider: IntegrationProvider
    name: str
    description: str
    category: str
    logo: str
    auth_kind: str
    available: bool = True
    coming_soon: bool = False
    tools: list[str] = Field(default_factory=list)


class OAuthStartResponse(DomainModel):
    authorization_url: str
    state: str


#: Tool-name prefix -> the provider whose credentials that tool needs. Single source of
#: truth for turning a capability list into the connections it requires.
TOOL_PROVIDER_PREFIXES: dict[str, IntegrationProvider] = {
    "github": IntegrationProvider.GITHUB,
    "jira": IntegrationProvider.JIRA,
    "gmail": IntegrationProvider.GOOGLE,
    "drive": IntegrationProvider.GOOGLE,
    "sheets": IntegrationProvider.GOOGLE,
    "calendar": IntegrationProvider.GOOGLE,
    "docs": IntegrationProvider.GOOGLE,
}


def provider_for_tool(tool: str) -> IntegrationProvider | None:
    """The provider a tool name belongs to, or ``None`` when it needs none."""
    prefix = str(tool).split(".", 1)[0].strip().lower()
    return TOOL_PROVIDER_PREFIXES.get(prefix)


def canonical_providers(tools: Iterable[str], declared: Iterable[str] | None = None) -> list[str]:
    """Normalised, de-duplicated provider names for a Buttlr.

    Accepts provider names and tool prefixes alike, so a configuration that says ``gmail``
    and one that says ``google`` resolve to the same connection. Unknown names are dropped
    rather than guessed at.
    """
    resolved: list[str] = []
    for value in declared or []:
        try:
            provider = IntegrationProvider(str(value).strip().lower())
        except ValueError:
            provider = provider_for_tool(str(value).strip().lower())
            if provider is None and "." not in str(value):
                provider = TOOL_PROVIDER_PREFIXES.get(str(value).strip().lower())
        if provider is not None and provider.value not in resolved:
            resolved.append(provider.value)
    for tool in tools or []:
        provider = provider_for_tool(str(tool))
        if provider is not None and provider.value not in resolved:
            resolved.append(provider.value)
    return resolved
