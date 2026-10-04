"""Model providers a workspace configures for itself.

No network is involved: availability for the hosted providers is a credential check, and the
local provider is asserted through its stored configuration rather than a live server.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.container import Container
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from app.schemas.models import ModelProviderUpdate
from app.schemas.organization import MemberInvite, OrganizationCreate
from tests.conftest import auth


async def world(container: Container):
    owner = await container.auth.principal_from_token(
        (await container.auth.dev_login("models-owner@example.com", "Owner")).access_token
    )
    organization = await container.organizations.create(
        owner, OrganizationCreate(name="Model Corp")
    )
    owner = owner.model_copy(update={"organization_id": organization.id})
    await container.organizations.invite(
        owner, organization.id, MemberInvite(email="models-member@example.com", role="member")
    )
    member = await container.auth.principal_from_token(
        (await container.auth.dev_login("models-member@example.com", "Member")).access_token
    )
    return owner, member, organization


async def test_the_catalogue_covers_every_provider_and_leads_with_nothing_configured(
    container: Container,
) -> None:
    _, _, organization = await world(container)
    entries = {entry.provider: entry for entry in await container.models.entries(organization.id)}

    assert set(entries) == {"openai", "anthropic", "google", "ollama", "heuristic"}
    assert entries["heuristic"].configured is True, "the offline planner is always available"
    assert entries["heuristic"].kind == "builtin"
    for provider in ("openai", "anthropic", "google", "ollama"):
        assert entries[provider].configured is False, provider
        assert entries[provider].source is None
    assert entries["ollama"].requires_base_url is True
    assert entries["ollama"].requires_key is False


async def test_only_an_admin_can_configure_a_provider(container: Container) -> None:
    owner, member, organization = await world(container)
    with pytest.raises(PermissionDeniedError):
        await container.models.set_provider(
            member, organization.id, "openai", ModelProviderUpdate(api_key="sk-member")
        )
    configured = await container.models.set_provider(
        owner, organization.id, "openai", ModelProviderUpdate(api_key="sk-owner-key")
    )
    assert configured.configured is True


async def test_a_workspace_key_makes_that_provider_usable(container: Container) -> None:
    owner, _, organization = await world(container)
    assert "openai" not in await container.models.available(organization.id)

    entry = await container.models.set_provider(
        owner, organization.id, "openai", ModelProviderUpdate(api_key="sk-workspace-key")
    )
    assert entry.source == "workspace"
    assert entry.configured is True
    assert "openai" in await container.models.available(organization.id)

    # A different workspace with no key of its own stays unconfigured: the key is scoped.
    other = await container.organizations.create(owner, OrganizationCreate(name="Other Corp"))
    assert "openai" not in await container.models.available(other.id)


async def test_the_local_provider_needs_an_endpoint(container: Container) -> None:
    owner, _, organization = await world(container)
    with pytest.raises(ValidationError):
        await container.models.set_provider(
            owner, organization.id, "ollama", ModelProviderUpdate(api_key="unused")
        )
    with pytest.raises(ValidationError):
        await container.models.set_provider(
            owner, organization.id, "ollama", ModelProviderUpdate(base_url="localhost:11434")
        )

    entry = await container.models.set_provider(
        owner, organization.id, "ollama", ModelProviderUpdate(base_url="http://localhost:11434")
    )
    assert entry.configured is True
    assert entry.base_url == "http://localhost:11434"
    assert entry.source == "workspace"


async def test_the_builtin_planner_cannot_be_configured(container: Container) -> None:
    owner, _, organization = await world(container)
    with pytest.raises(ValidationError):
        await container.models.set_provider(
            owner, organization.id, "heuristic", ModelProviderUpdate(api_key="nope")
        )
    with pytest.raises(NotFoundError):
        await container.models.set_provider(
            owner, organization.id, "not-a-provider", ModelProviderUpdate(api_key="nope")
        )


async def test_a_model_choice_can_be_saved_and_removed(container: Container) -> None:
    owner, _, organization = await world(container)
    entry = await container.models.set_provider(
        owner,
        organization.id,
        "openai",
        ModelProviderUpdate(api_key="sk-key", model="gpt-4o"),
    )
    assert entry.model == "gpt-4o"

    keep = await container.models.set_provider(
        owner, organization.id, "openai", ModelProviderUpdate(model="gpt-4o-mini")
    )
    assert keep.model == "gpt-4o-mini"
    assert keep.configured is True, "updating the model must not drop the stored key"

    await container.models.clear_provider(owner, organization.id, "openai")
    assert "openai" not in await container.models.available(organization.id)
    entries = {entry.provider: entry for entry in await container.models.entries(organization.id)}
    assert entries["openai"].configured is False


# ---- HTTP surface ----------------------------------------------------------


def test_the_models_endpoints_are_scoped_and_never_return_a_key(client: TestClient) -> None:
    owner_token = client.post(
        "/api/v1/auth/dev/login", json={"email": "http-owner@example.com"}
    ).json()["access_token"]
    created = client.post(
        "/api/v1/organizations", json={"name": "Http Models"}, headers=auth(owner_token)
    )
    organization_id = created.json()["id"]
    client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={"email": "http-member@example.com", "role": "member"},
        headers=auth(owner_token),
    )
    member_token = client.post(
        "/api/v1/auth/dev/login", json={"email": "http-member@example.com"}
    ).json()["access_token"]

    listing = client.get(
        f"/api/v1/organizations/{organization_id}/models", headers=auth(member_token)
    )
    assert listing.status_code == 200
    assert {entry["provider"] for entry in listing.json()} == {
        "openai",
        "anthropic",
        "google",
        "ollama",
        "heuristic",
    }

    forbidden = client.put(
        f"/api/v1/organizations/{organization_id}/models/openai",
        json={"api_key": "sk-member"},
        headers=auth(member_token),
    )
    assert forbidden.status_code == 403

    saved = client.put(
        f"/api/v1/organizations/{organization_id}/models/google",
        json={"api_key": "AIza-workspace-gemini-key"},
        headers=auth(owner_token),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["configured"] is True
    assert saved.json()["source"] == "workspace"
    assert "AIza-workspace-gemini-key" not in saved.text
    assert "api_key" not in saved.json()

    available = client.get(
        f"/api/v1/organizations/{organization_id}/models/available", headers=auth(member_token)
    )
    assert available.status_code == 200
    providers = {entry["provider"] for entry in available.json()}
    assert "google" in providers, "a configured provider is offered to the builder"
    assert "openai" not in providers
    assert "heuristic" in providers

    removed = client.delete(
        f"/api/v1/organizations/{organization_id}/models/google", headers=auth(owner_token)
    )
    assert removed.status_code == 204
