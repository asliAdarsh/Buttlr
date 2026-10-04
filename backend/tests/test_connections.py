"""Connections made in the application, per person.

The network edge (``probe`` and ``_load_resources``) is stubbed: these tests are about who may
connect what, which account a run uses, and what the API is allowed to return.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.container import Container
from app.core.errors import PermissionDeniedError, ValidationError
from app.integrations.service import IntegrationService
from app.runtime.executor import ExecutionJob
from app.runtime.permissions.engine import AccessContext
from app.runtime.planner.base import Plan, Planner
from app.runtime.tools.base import Tool, ToolContext, ToolResult
from app.runtime.tools.registry import ToolRegistry
from app.schemas.buttlr import ButtlrCreate, PermissionGrant
from app.schemas.enums import (
    ButtlrStatus,
    ExecutionStatus,
    ExecutionTrigger,
    GrantSubject,
    IntegrationProvider,
    IntegrationScope,
    OrgRole,
    Permission,
    RiskLevel,
)
from app.schemas.integration import IntegrationConnectToken, OAuthClientUpdate
from app.schemas.organization import MemberInvite, OrganizationCreate

GITHUB = IntegrationProvider.GITHUB


@pytest.fixture()
def offline_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for the provider's HTTP API at the service's own edge."""

    async def fake_probe(self: IntegrationService, provider, credentials) -> str | None:
        if provider is GITHUB:
            return "octocat" if credentials.get("token") else None
        return "someone@example.com"

    async def fake_resources(self: IntegrationService, provider, credentials):
        if provider is GITHUB:
            return [
                {"id": "acme/backend", "name": "backend", "kind": "repository", "meta": {}},
                {"id": "acme/web", "name": "web", "kind": "repository", "meta": {}},
            ]
        return []

    monkeypatch.setattr(IntegrationService, "probe", fake_probe)
    monkeypatch.setattr(IntegrationService, "_load_resources", fake_resources)


async def login(container: Container, email: str):
    tokens = await container.auth.dev_login(email, email.split("@")[0].title())
    return await container.auth.principal_from_token(tokens.access_token)


async def workspace(container: Container):
    """Owner Alice, plain member Bob, both in one organization."""
    alice = await login(container, "alice@example.com")
    organization = await container.organizations.create(
        alice, OrganizationCreate(name="Connections Corp")
    )
    alice = alice.model_copy(update={"organization_id": organization.id})
    await container.organizations.invite(
        alice, organization.id, MemberInvite(email="bob@example.com", role=OrgRole.MEMBER)
    )
    bob = await login(container, "bob@example.com")
    return alice, bob, organization


async def connect(
    container: Container,
    principal,
    organization,
    token: str,
    scope: IntegrationScope,
    provider: IntegrationProvider = GITHUB,
    **extra,
):
    return await container.integrations.connect_token(
        principal,
        organization.id,
        IntegrationConnectToken(provider=provider, token=token, scope=scope, **extra),
    )


async def test_a_member_connects_their_own_account(container: Container, offline_provider) -> None:
    _, bob, organization = await workspace(container)
    public = await connect(container, bob, organization, "ghp_bob_token_value", IntegrationScope.PERSONAL)

    assert public.scope is IntegrationScope.PERSONAL
    assert public.owner_id == bob.user_id
    assert public.account == "octocat"
    assert public.resources and public.resources[0].id == "acme/backend"

    # It is Bob's document, and Alice (an owner) can see it, but it is not the shared one.
    shared = await container.integrations.get(organization.id, GITHUB)
    assert shared is None


async def test_a_member_cannot_connect_a_shared_account(
    container: Container, offline_provider
) -> None:
    _, bob, organization = await workspace(container)
    with pytest.raises(PermissionDeniedError):
        await connect(container, bob, organization, "ghp_bob_token_value", IntegrationScope.ORGANIZATION)


async def test_an_admin_can_connect_a_shared_account(container: Container, offline_provider) -> None:
    alice, _, organization = await workspace(container)
    public = await connect(container, alice, organization, "ghp_shared_token_value", IntegrationScope.ORGANIZATION)
    assert public.scope is IntegrationScope.ORGANIZATION
    assert public.owner_id is None
    stored = await container.integrations.get(organization.id, GITHUB)
    assert stored is not None and stored.id == "github"


async def test_listing_shows_the_shared_connections_and_your_own_only(
    container: Container, offline_provider
) -> None:
    alice, bob, organization = await workspace(container)
    await connect(container, alice, organization, "ghp_shared_token_value", IntegrationScope.ORGANIZATION)
    await connect(container, bob, organization, "ghp_bob_token_value", IntegrationScope.PERSONAL)
    await connect(
        container,
        bob,
        organization,
        "jira_bob_token_value",
        IntegrationScope.PERSONAL,
        provider=IntegrationProvider.JIRA,
        base_url="https://acme.atlassian.net",
        email="bob@example.com",
    )

    for_bob = await container.integrations.list(organization.id, viewer_id=bob.user_id)
    assert len(for_bob) == 3
    assert {item.scope for item in for_bob} == {IntegrationScope.ORGANIZATION, IntegrationScope.PERSONAL}
    assert all(item.owner_id in (None, bob.user_id) for item in for_bob)

    # Carol's connection is invisible to Bob, and visible to an administrator.
    carol = await login(container, "carol@example.com")
    await container.organizations.invite(
        alice, organization.id, MemberInvite(email="carol@example.com", role=OrgRole.MEMBER)
    )
    await connect(container, carol, organization, "ghp_carol_token_value", IntegrationScope.PERSONAL)

    for_bob = await container.integrations.list(organization.id, viewer_id=bob.user_id)
    assert len(for_bob) == 3, "another person's connection must not appear"
    for_alice = await container.integrations.list(
        organization.id, viewer_id=alice.user_id, is_admin=True
    )
    assert len(for_alice) == 4
    assert {item.owner_name for item in for_alice} == {None, "Bob", "Carol"}


async def test_a_run_uses_the_accessing_persons_account(container: Container, offline_provider) -> None:
    alice, bob, organization = await workspace(container)
    await connect(container, alice, organization, "ghp_alice_token_value", IntegrationScope.PERSONAL)
    await connect(container, bob, organization, "ghp_bob_token_value", IntegrationScope.PERSONAL)

    buttlr = await container.buttlrs.create(
        alice,
        organization.id,
        ButtlrCreate(name="PR Guardian", tools=[], integrations=[GITHUB.value], status=ButtlrStatus.ACTIVE),
    )
    assert buttlr.created_by == alice.user_id

    assert (await container.integrations.credentials_for(organization.id, buttlr, bob.user_id))[
        "github"
    ]["token"] == "ghp_bob_token_value"
    assert (await container.integrations.credentials_for(organization.id, buttlr, alice.user_id))[
        "github"
    ]["token"] == "ghp_alice_token_value"


async def test_a_run_falls_back_to_the_owners_account_then_the_shared_one(
    container: Container, offline_provider
) -> None:
    alice, bob, organization = await workspace(container)
    await connect(container, alice, organization, "ghp_alice_token_value", IntegrationScope.PERSONAL)
    buttlr = await container.buttlrs.create(
        alice,
        organization.id,
        ButtlrCreate(name="PR Guardian", tools=[], integrations=[GITHUB.value]),
    )

    # Bob has nothing of his own: the Buttlr owner's account is used.
    assert (await container.integrations.credentials_for(organization.id, buttlr, bob.user_id))[
        "github"
    ]["token"] == "ghp_alice_token_value"

    await connect(container, alice, organization, "ghp_shared_token_value", IntegrationScope.ORGANIZATION)
    await container.repo.delete(
        "organizations/" + organization.id + "/integrations", f"github:{alice.user_id}"
    )
    # With the owner's account gone, the workspace connection takes over.
    assert (await container.integrations.credentials_for(organization.id, buttlr, bob.user_id))[
        "github"
    ]["token"] == "ghp_shared_token_value"


async def test_another_persons_connection_is_never_used(
    container: Container, offline_provider
) -> None:
    alice, bob, organization = await workspace(container)
    carol = await login(container, "carol@example.com")
    await container.organizations.invite(
        alice, organization.id, MemberInvite(email="carol@example.com", role=OrgRole.MEMBER)
    )
    await connect(container, carol, organization, "ghp_carol_token_value", IntegrationScope.PERSONAL)

    buttlr = await container.buttlrs.create(
        alice,
        organization.id,
        ButtlrCreate(name="PR Guardian", tools=[], integrations=[GITHUB.value]),
    )
    # Neither the actor nor the owner is Carol, so her account contributes nothing.
    assert await container.integrations.credentials_for(organization.id, buttlr, bob.user_id) == {}


class ProbeTool(Tool):
    """Records the credentials the runtime handed it."""

    name = "github.probe"
    description = "Report which GitHub account the run is using."
    integration = "github"
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        pass

    input_model = Input

    def __init__(self) -> None:
        self.seen: list[dict] = []

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        self.seen.append(dict(ctx.credential("github")))
        return ToolResult.success(f"using {ctx.credential('github').get('token', 'nothing')}")


class OneShotPlanner(Planner):
    id = "oneshot"

    def __init__(self) -> None:
        self.calls = 0

    async def next(self, request):  # type: ignore[override]
        self.calls += 1
        if self.calls == 1:
            return Plan.call(ProbeTool.name, {}, thought="See which account is in play.")
        return Plan.finish("Done.")


async def test_the_runtime_hands_the_run_the_accessing_persons_credentials(
    container: Container, offline_provider
) -> None:
    alice, bob, organization = await workspace(container)
    await connect(container, alice, organization, "ghp_alice_token_value", IntegrationScope.PERSONAL)
    await connect(container, bob, organization, "ghp_bob_token_value", IntegrationScope.PERSONAL)

    tool = ProbeTool()
    registry = ToolRegistry([tool])
    container.registry = registry
    container.executor.registry = registry
    container.buttlrs.registry = registry

    buttlr = await container.buttlrs.create(
        alice,
        organization.id,
        ButtlrCreate(
            name="PR Guardian",
            tools=[ProbeTool.name],
            integrations=[GITHUB.value],
            status=ButtlrStatus.ACTIVE,
            permissions=[
                PermissionGrant(
                    subject_type=GrantSubject.USER,
                    subject=bob.user_id,
                    permission=Permission.ADMIN,
                )
            ],
        ),
    )

    for principal, role in ((bob, OrgRole.MEMBER), (alice, OrgRole.OWNER)):
        planner = OneShotPlanner()
        container.executor._select_planner = lambda _buttlr, p=planner: _resolved(p)  # type: ignore[assignment]
        execution = await container.executions.create(
            organization.id, buttlr, ExecutionTrigger.MANUAL, "Which account?", requested_by=principal.user_id
        )
        access = AccessContext(
            user_id=principal.user_id,
            org_role=role,
            team_ids=(),
            settings=organization.settings,
        )
        outcome = await container.executor.run(
            ExecutionJob(
                organization=organization,
                buttlr=buttlr,
                execution=execution,
                goal="Which account?",
                trigger=ExecutionTrigger.MANUAL,
                requested_by=principal.user_id,
                access=access,
            )
        )
        assert outcome.status == ExecutionStatus.COMPLETED

    assert [seen.get("token") for seen in tool.seen] == [
        "ghp_bob_token_value",
        "ghp_alice_token_value",
    ]


async def _resolved(planner: Planner) -> Planner:
    return planner


async def test_deploy_is_allowed_when_the_owner_connected_their_own_account(
    container: Container, offline_provider
) -> None:
    alice, _, organization = await workspace(container)
    buttlr = await container.buttlrs.create(
        alice,
        organization.id,
        ButtlrCreate(name="PR Guardian", tools=[], integrations=[GITHUB.value]),
    )
    with pytest.raises(ValidationError):
        await container.buttlrs.deploy(alice, organization.id, buttlr.id)

    await connect(container, alice, organization, "ghp_alice_token_value", IntegrationScope.PERSONAL)
    deployed = await container.buttlrs.deploy(alice, organization.id, buttlr.id)
    assert deployed.status.value == "active"


# ---- workspace OAuth applications -----------------------------------------


async def test_a_workspace_can_register_its_own_oauth_app(
    container: Container, offline_provider
) -> None:
    alice, bob, organization = await workspace(container)

    with pytest.raises(PermissionDeniedError):
        await container.integrations.set_oauth_client(
            bob,
            organization.id,
            GITHUB,
            OAuthClientUpdate(client_id="Iv1.bobclient", client_secret="nope"),
        )

    status = await container.integrations.set_oauth_client(
        alice,
        organization.id,
        GITHUB,
        OAuthClientUpdate(client_id="Iv1.workspace", client_secret="workspace-secret"),
    )
    assert status.configured is True
    assert status.source == "workspace"
    assert status.client_id == "Iv1.workspace"
    assert "workspace-secret" not in status.model_dump_json()

    # The deployment has no OAuth credentials at all: the workspace's app is what makes
    # connecting possible, and the secret never leaves the service.
    assert not container.settings.github_oauth_client_id
    started = await container.integrations.oauth_start(
        organization.id,
        GITHUB,
        "http://localhost:8000/api/v1/integrations/oauth/github/callback",
        user_id=bob.user_id,
        scope=IntegrationScope.PERSONAL,
    )
    assert "client_id=Iv1.workspace" in started.authorization_url

    from app.integrations.oauth import verify_state

    claims = verify_state(started.state, container.settings.dev_auth_secret)
    assert claims["user"] == bob.user_id
    assert claims["scope"] == "personal"


async def test_oauth_says_what_to_do_when_no_app_is_configured(container: Container) -> None:
    alice, _, organization = await workspace(container)
    with pytest.raises(ValidationError) as error:
        await container.integrations.oauth_start(
            organization.id,
            IntegrationProvider.GOOGLE,
            "http://localhost:8000/api/v1/integrations/oauth/google/callback",
            user_id=alice.user_id,
        )
    assert "OAuth app" in error.value.message
    assert "Integrations" in error.value.message


async def test_clearing_the_workspace_app_falls_back_to_the_deployment(
    container: Container, offline_provider
) -> None:
    alice, _, organization = await workspace(container)
    await container.integrations.set_oauth_client(
        alice, organization.id, GITHUB, OAuthClientUpdate(client_id="Iv1.workspace", client_secret="s")
    )
    await container.integrations.clear_oauth_client(alice, organization.id, GITHUB)
    statuses = await container.integrations.oauth_clients(organization.id)
    github = next(item for item in statuses if item.provider is GITHUB)
    assert github.source is None
    assert github.configured is False


async def test_a_personal_oauth_callback_without_an_owner_is_rejected(
    container: Container, offline_provider
) -> None:
    _, _, organization = await workspace(container)
    from app.integrations.oauth import sign_state

    state = sign_state(
        GITHUB,
        organization.id,
        "http://localhost:8000/api/v1/integrations/oauth/github/callback",
        container.settings.dev_auth_secret,
        user_id="",
        scope="personal",
    )
    with pytest.raises(ValidationError):
        await container.integrations.connect_oauth_callback(organization.id, GITHUB, "code", state)


async def test_a_callback_cannot_be_replayed_against_another_organization(
    container: Container, offline_provider
) -> None:
    alice, _, organization = await workspace(container)
    other = await container.organizations.create(alice, OrganizationCreate(name="Other Corp"))
    from app.integrations.oauth import sign_state

    state = sign_state(
        GITHUB,
        other.id,
        "http://localhost:8000/api/v1/integrations/oauth/github/callback",
        container.settings.dev_auth_secret,
        user_id=alice.user_id,
    )
    with pytest.raises(ValidationError):
        await container.integrations.connect_oauth_callback(organization.id, GITHUB, "code", state)
