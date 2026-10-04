"""Development seeding — the demo story in one call.

Creates **Acme Technologies**, the Engineering team, a team lead, and the `PR Guardian`
Buttlr built through the real natural-language builder. GitHub is connected only when a
working token is supplied, because Buttlr never pretends a credential works.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import ContainerDep
from app.core.errors import ConflictError, ValidationError
from app.core.logging import get_logger
from app.database.base import eq
from app.database.repository import Paths
from app.schemas.buttlr import Buttlr, ButtlrDraftRequest, PermissionGrant
from app.schemas.enums import (
    GrantSubject,
    IntegrationProvider,
    IntegrationScope,
    IntegrationStatus,
    NotificationKind,
    OrgRole,
    Permission,
)
from app.schemas.integration import IntegrationConnectToken
from app.schemas.organization import MemberInvite, OrganizationCreate, TeamCreate, UserUpdate

logger = get_logger(__name__)
router = APIRouter(tags=["dev"])

DEMO_PROMPT_GITHUB = (
    "Monitor our selected GitHub repositories every morning. Analyse new pull requests for "
    "bugs, security issues, missing tests and unresolved review comments. Summarise the "
    "important findings. If a critical issue is found, open a GitHub issue and ask the "
    "Engineering Lead for approval before creating it."
)
DEMO_PROMPT_JIRA = (
    "Monitor our selected GitHub repositories every morning. Analyse new pull requests for "
    "bugs, security issues, missing tests and unresolved review comments. Summarise the "
    "important findings. If a critical issue is found, prepare a Jira ticket and ask the "
    "Engineering Lead for approval before creating it."
)

class SeedRequest(BaseModel):
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, max_length=80)
    github_token: str | None = Field(default=None, min_length=8)
    reset: bool = False


class SeedResponse(BaseModel):
    user_id: str
    organization_id: str
    team_id: str
    buttlr_id: str
    lead_email: str
    github_connected: bool
    deployed: bool
    created: bool


async def _purge(container: ContainerDep, organization_id: str) -> None:
    for path in (
        Paths.buttlrs(organization_id),
        Paths.teams(organization_id),
        Paths.executions(organization_id),
        Paths.approvals(organization_id),
        Paths.audit_logs(organization_id),
        Paths.notifications(organization_id),
        Paths.integrations(organization_id),
        Paths.members(organization_id),
    ):
        await container.store.delete_many(path, [])
    await container.repo.delete(Paths.ORGANIZATIONS, organization_id)


@router.post("/dev/seed", response_model=SeedResponse, status_code=status.HTTP_201_CREATED)
async def seed(container: ContainerDep, payload: SeedRequest | None = None) -> SeedResponse:
    settings = container.settings
    if settings.auth_mode != "dev":
        raise ValidationError(
            "Demo seeding is only available when AUTH_MODE=dev.", code="seed_disabled"
        )
    request = payload or SeedRequest()

    email = str(request.email or "owner@acme.example.com")
    tokens = await container.auth.dev_login(email, request.display_name or "Adarsh Verma")
    principal = await container.auth.principal_from_token(tokens.access_token)

    existing = await container.repo.store.query_one(
        Paths.ORGANIZATIONS, [eq("slug", "acme-technologies")]
    )
    created = existing is None
    if existing is not None and request.reset:
        await _purge(container, existing["id"])
        existing = None
        created = True
    if existing is None and await container.repo.store.query_one(
        Paths.ORGANIZATIONS, [eq("slug", "acme-technologies")]
    ):
        raise ConflictError("The demo organization already exists. Pass reset=true to rebuild it.")
    if existing is not None:
        organization = await container.organizations.get(existing["id"])
        teams = await container.teams.list(organization.id)
        team = next((t for t in teams if t.name == "Engineering"), teams[0] if teams else None)
        if team is None:
            raise ConflictError("The demo organization is incomplete. Pass reset=true to rebuild it.")
        buttlrs = await container.buttlrs.list(organization.id)
        if not buttlrs:
            raise ConflictError("The demo organization is incomplete. Pass reset=true to rebuild it.")
        github_connected = any(
            integration.provider == IntegrationProvider.GITHUB
            and integration.status == IntegrationStatus.CONNECTED
            for integration in await container.integrations.list(
                organization.id, viewer_id=principal.user_id, is_admin=True
            )
        )
        return SeedResponse(
            user_id=principal.user_id,
            organization_id=organization.id,
            team_id=team.id,
            buttlr_id=buttlrs[0].id,
            lead_email="lead@acme.example.com",
            github_connected=github_connected,
            deployed=buttlrs[0].status.value == "active",
            created=False,
        )

    organization = await container.organizations.create(
        principal,
        OrganizationCreate(
            name="Acme Technologies",
            description="A product engineering company running its AI workforce on Buttlr.",
            logo_emoji="🏢",
        ),
    )
    await container.auth.update_user(
        principal.user_id,
        UserUpdate(default_organization_id=organization.id),
    )
    principal = principal.model_copy(
        update={"organization_id": organization.id, "role": OrgRole.OWNER}
    )

    team = await container.teams.create(
        principal,
        organization.id,
        TeamCreate(
            name="Engineering",
            description="Builds and ships the Acme product.",
            emoji="⚙️",
            color="violet",
            member_ids=[principal.user_id],
        ),
    )
    lead = await container.organizations.invite(
        principal,
        organization.id,
        MemberInvite(email="lead@acme.example.com", role=OrgRole.ADMIN, team_ids=[team.id]),
    )
    lead_id = lead.user.id if lead.user else None

    github_connected = False
    jira_connected = any(
        integration.provider == IntegrationProvider.JIRA
        for integration in await container.integrations.list(
            organization.id, viewer_id=principal.user_id, is_admin=True
        )
    )
    if request.github_token:
        try:
            await container.integrations.connect_token(
                principal,
                organization.id,
                IntegrationConnectToken(
                    provider=IntegrationProvider.GITHUB,
                    token=request.github_token,
                    scope=IntegrationScope.ORGANIZATION,
                    account=email,
                ),
            )
            github_connected = True
        except Exception as exc:
            logger.warning("seed: GitHub connect failed: %s", exc)
            await container.notifications.notify(
                organization.id,
                NotificationKind.INTEGRATION_ERROR,
                title="GitHub could not be connected",
                body=str(exc),
                link="/integrations",
            )

    prompt = DEMO_PROMPT_JIRA if jira_connected else DEMO_PROMPT_GITHUB
    draft = await container.buttlrs.draft(
        principal,
        organization.id,
        ButtlrDraftRequest(prompt=prompt, organization_id=organization.id, team_id=team.id),
    )
    permissions = [
        PermissionGrant(
            subject_type=GrantSubject.TEAM, subject=team.id, permission=Permission.ASK
        )
    ]
    if lead_id:
        permissions.append(
            PermissionGrant(
                subject_type=GrantSubject.USER, subject=lead_id, permission=Permission.APPROVE
            )
        )
    payload = draft.draft.model_copy(
        update={
            "team_id": team.id,
            "department": "Engineering",
            "permissions": permissions,
        }
    )
    buttlr = await container.buttlrs.create(principal, organization.id, payload)

    deployed = False
    if github_connected or jira_connected:
        try:
            buttlr = await container.buttlrs.deploy(principal, organization.id, buttlr.id)
            deployed = buttlr.status.value == "active"
        except Exception as exc:
            logger.warning("seed: deploy failed: %s", exc)
            await container.notifications.notify(
                organization.id,
                NotificationKind.SYSTEM,
                title=f"{buttlr.name} is ready to deploy",
                body=str(exc),
                link=f"/buttlrs/{buttlr.id}",
            )
    else:
        await container.notifications.notify(
            organization.id,
            NotificationKind.SYSTEM,
            title=f"{buttlr.name} needs an integration",
            body="Connect GitHub in Integrations, then deploy PR Guardian.",
            link="/integrations",
        )

    await container.notifications.notify(
        organization.id,
        NotificationKind.SYSTEM,
        title="Acme Technologies is ready",
        body="Your organization, Engineering team and PR Guardian Buttlr are set up.",
        link="/overview",
    )

    logger.info("seeded Acme Technologies org=%s buttlr=%s github=%s", organization.id, buttlr.id, github_connected)
    return SeedResponse(
        user_id=principal.user_id,
        organization_id=organization.id,
        team_id=team.id,
        buttlr_id=buttlr.id,
        lead_email="lead@acme.example.com",
        github_connected=github_connected,
        deployed=deployed,
        created=created,
    )


__all__ = ["Buttlr", "SeedRequest", "SeedResponse", "router"]
