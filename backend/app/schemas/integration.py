"""Integrations and their public projection.

Credentials live in the stored document only; ``to_public`` is the only shape that ever
reaches an HTTP response.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import DomainModel, utcnow
from app.schemas.enums import IntegrationProvider, IntegrationStatus


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
    account: str | None = None
    base_url: str | None = None
    email: str | None = None
    label: str | None = None


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
