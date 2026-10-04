"""Connections between an organization and the tools its Buttlrs use.

Credentials are encrypted at rest with ``app.core.crypto`` and never leave this
module in plaintext: every public method returns a ``to_public()`` projection.
Only :meth:`IntegrationService.credentials_for` hands decrypted credentials out,
and only to the runtime, keyed by provider.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.core.config import Settings
from app.core.crypto import seal_credentials, unseal_credentials
from app.core.errors import (
    IntegrationError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.core.logging import get_logger
from app.database.base import Sort, Store
from app.database.repository import Paths, Repository
from app.integrations.github import GitHubClient
from app.integrations.google import GoogleClient
from app.integrations.jira import JiraClient
from app.integrations.oauth import (
    build_authorization_url,
    exchange_code,
    provider_display_name,
    require_provider_config,
    sign_state,
    verify_state,
)
from app.schemas.auth import Principal
from app.schemas.buttlr import Buttlr
from app.schemas.common import utcnow
from app.schemas.enums import (
    ActorType,
    AuditAction,
    IntegrationProvider,
    IntegrationStatus,
    OrgRole,
)
from app.schemas.integration import (
    TOOL_PROVIDER_PREFIXES,
    Integration,
    IntegrationCatalogEntry,
    IntegrationConnectToken,
    IntegrationPublic,
    IntegrationResource,
    IntegrationScopesUpdate,
    OAuthStartResponse,
)

logger = get_logger(__name__)

ROLE_RANK: dict[OrgRole, int] = {
    OrgRole.MEMBER: 0,
    OrgRole.ADMIN: 1,
    OrgRole.OWNER: 2,
}

GITHUB_TOOLS = (
    "github.list_repositories",
    "github.list_pull_requests",
    "github.get_pull_request",
    "github.list_pull_request_files",
    "github.list_pull_request_comments",
    "github.list_issues",
    "github.create_issue",
    "github.add_comment",
)
JIRA_TOOLS = (
    "jira.search_issues",
    "jira.create_issue",
    "jira.update_issue",
    "jira.add_comment",
)
GOOGLE_TOOLS = (
    "gmail.search_messages",
    "gmail.get_message",
    "gmail.send_message",
    "drive.search_files",
    "drive.get_file",
    "sheets.read_range",
    "sheets.write_range",
    "calendar.list_events",
    "calendar.create_event",
    "docs.get_document",
)
TOOL_PROVIDERS: dict[str, IntegrationProvider] = TOOL_PROVIDER_PREFIXES

#: Statuses that must never yield credentials.
_UNUSABLE_STATUSES = {IntegrationStatus.DISCONNECTED, IntegrationStatus.ERROR}

_GITHUB_API = "https://api.github.com"


class IntegrationService:
    """Owns the lifecycle of an organization's third-party connections."""

    def __init__(self, store: Store, audit: Any, settings: Settings) -> None:
        self.store = store
        self.audit = audit
        self.settings = settings
        self.repo = Repository(store)

    # ---- catalogue --------------------------------------------------------

    async def catalogue(self) -> list[IntegrationCatalogEntry]:
        """Every connection Buttlr offers, with the tools it unlocks."""
        return [
            IntegrationCatalogEntry(
                provider=IntegrationProvider.GITHUB,
                name="GitHub",
                description=(
                    "Read pull requests, issues and repositories, open issues and "
                    "comment on discussions."
                ),
                category="Developer tools",
                logo="🐙",
                auth_kind="token",
                available=True,
                tools=list(GITHUB_TOOLS),
            ),
            IntegrationCatalogEntry(
                provider=IntegrationProvider.GOOGLE,
                name="Google Workspace",
                description=(
                    "Search and send Gmail, find Drive files, read and write Sheets, "
                    "manage the calendar and read Docs."
                ),
                category="Productivity",
                logo="📧",
                auth_kind="oauth",
                available=True,
                tools=list(GOOGLE_TOOLS),
            ),
            IntegrationCatalogEntry(
                provider=IntegrationProvider.JIRA,
                name="Jira",
                description=(
                    "Search issues with JQL, create and update issues, and add comments."
                ),
                category="Project management",
                logo="🎫",
                auth_kind="token",
                available=True,
                tools=list(JIRA_TOOLS),
            ),
        ]

    # ---- reads ------------------------------------------------------------

    async def list(self, org_id: str) -> list[IntegrationPublic]:
        rows = await self.repo.list(
            Paths.integrations(org_id), order_by="created_at", sort=Sort.DESC
        )
        return [self._to_model(row).to_public() for row in rows]

    async def get(
        self, org_id: str, provider: IntegrationProvider | str
    ) -> Integration | None:
        row = await self._load(org_id, provider)
        return self._to_model(row) if row else None

    async def credentials_for(
        self, org_id: str, buttlr: Buttlr
    ) -> dict[str, dict[str, Any]]:
        """Decrypted credentials for every provider this Buttlr can reach.

        A provider that isn't connected contributes nothing, so the tool fails
        closed with its own actionable message.
        """
        wanted = _providers_for(buttlr)
        if not wanted:
            return {}
        rows = await self.repo.list(Paths.integrations(org_id), order_by=None)
        resolved: dict[str, dict[str, Any]] = {}
        for row in rows:
            integration = self._to_model(row)
            if integration.provider not in wanted:
                continue
            if integration.status in _UNUSABLE_STATUSES:
                continue
            if not integration.credentials:
                continue
            try:
                resolved[integration.provider.value] = unseal_credentials(
                    integration.credentials
                )
            except Exception:
                logger.warning(
                    "could not unseal %s credentials for org %s",
                    integration.provider.value,
                    org_id,
                )
        return resolved

    # ---- token connections ------------------------------------------------

    async def connect_token(
        self, principal: Principal, org_id: str, payload: IntegrationConnectToken
    ) -> IntegrationPublic:
        """Connect GitHub or Jira with a personal access token / API token."""
        await self._require_admin(org_id, principal)
        provider = payload.provider
        if provider is IntegrationProvider.GOOGLE:
            raise ValidationError(
                "Google Workspace connects through Google sign-in. "
                "Start the Google connection instead of pasting a token."
            )

        token = payload.token.strip()
        if not token:
            raise ValidationError("Enter the access token for this connection.")

        if provider is IntegrationProvider.GITHUB:
            credentials: dict[str, Any] = {"token": token}
            base_url = (payload.base_url or "").strip()
            if base_url:
                credentials["base_url"] = base_url.rstrip("/")
        else:
            base_url = (payload.base_url or "").strip().rstrip("/")
            email = (payload.email or "").strip()
            if not base_url:
                raise ValidationError(
                    "Enter your Jira site URL, for example "
                    "https://yourteam.atlassian.net."
                )
            if not email:
                raise ValidationError("Enter the email address for your Jira account.")
            credentials = {"base_url": base_url, "email": email, "api_token": token}

        account = await self.probe(provider, credentials)
        integration = Integration(
            id=provider.value,
            organization_id=org_id,
            provider=provider,
            display_name=payload.label or provider_display_name(provider),
            status=IntegrationStatus.CONNECTED,
            account=account or payload.account,
            credentials=seal_credentials(credentials),
            created_by=principal.user_id,
        )
        stored = await self._save(org_id, integration)
        refreshed = await self._refresh_resources(stored)
        await self._audit_connected(org_id, refreshed, principal)
        return refreshed.to_public()

    # ---- OAuth ------------------------------------------------------------

    async def oauth_start(
        self, org_id: str, provider: IntegrationProvider, redirect_uri: str
    ) -> OAuthStartResponse:
        """Build the provider consent URL and the signed state that binds it."""
        if not redirect_uri:
            raise ValidationError("A redirect URL is required to start the connection.")
        config = require_provider_config(provider, self.settings)
        state = sign_state(
            provider, org_id, redirect_uri, self.settings.dev_auth_secret
        )
        return OAuthStartResponse(
            authorization_url=build_authorization_url(config, redirect_uri, state),
            state=state,
        )

    async def connect_oauth_callback(
        self, org_id: str, provider: IntegrationProvider, code: str, state: str
    ) -> IntegrationPublic:
        """Finish an authorization-code flow and store the resulting credentials."""
        claims = verify_state(state, self.settings.dev_auth_secret)
        if str(claims.get("org") or "") != org_id:
            raise ValidationError(
                "This connection request belongs to a different organization. "
                "Please start again."
            )
        if str(claims.get("provider")) != provider.value:
            raise ValidationError(
                "This connection request was started for a different service. "
                "Please start again."
            )
        redirect_uri = str(claims.get("redirect") or "")
        if not code:
            raise ValidationError("That service didn't return an authorization code.")

        config = require_provider_config(provider, self.settings)
        token = await exchange_code(config, code, redirect_uri)
        credentials = self._credentials_from_token(provider, token)
        account = await self.probe(provider, credentials)

        integration = Integration(
            id=provider.value,
            organization_id=org_id,
            provider=provider,
            display_name=provider_display_name(provider),
            status=IntegrationStatus.CONNECTED,
            account=account,
            scopes=_granted_scopes(token, config.scopes),
            credentials=seal_credentials(credentials),
        )
        stored = await self._save(org_id, integration)
        refreshed = await self._refresh_resources(stored)
        await self._audit_connected(org_id, refreshed, actor=None)
        return refreshed.to_public()

    # ---- mutations --------------------------------------------------------

    async def update_scopes(
        self,
        principal: Principal,
        org_id: str,
        integration_id: str,
        payload: IntegrationScopesUpdate,
    ) -> IntegrationPublic:
        """Record which resources a Buttlr may reach.

        Resource selection is a UI preference: it narrows what is offered, and
        never widens what the credentials or the permission engine allow.
        """
        await self._require_admin(org_id, principal)
        integration = await self._require(org_id, integration_id)
        selected = {value for value in payload.resource_ids if value}
        integration.resources = [
            IntegrationResource(
                id=resource.id,
                name=resource.name,
                kind=resource.kind,
                selected=resource.id in selected,
                meta=resource.meta,
            )
            for resource in integration.resources
        ]
        integration.updated_at = utcnow()
        stored = await self._save(org_id, integration)
        return stored.to_public()

    async def disconnect(
        self, principal: Principal, org_id: str, integration_id: str
    ) -> None:
        await self._require_admin(org_id, principal)
        integration = await self._require(org_id, integration_id)
        await self.repo.delete(Paths.integrations(org_id), integration.id)
        await self.audit.record(
            org_id,
            AuditAction.INTEGRATION_DISCONNECTED,
            actor_type=ActorType.USER,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"Disconnected {provider_display_name(integration.provider)}.",
            target_type="integration",
            target_id=integration.id,
            metadata={"provider": integration.provider.value},
        )

    async def refresh_resources(
        self, principal: Principal, org_id: str, integration_id: str
    ) -> IntegrationPublic:
        await self._require_admin(org_id, principal)
        integration = await self._require(org_id, integration_id)
        return (await self._refresh_resources(integration)).to_public()

    # ---- provider probes --------------------------------------------------

    async def probe(
        self, provider: IntegrationProvider, credentials: dict[str, Any]
    ) -> str | None:
        """Verify a credential against the provider and return the account label."""
        if provider is IntegrationProvider.GITHUB:
            client = GitHubClient(
                str(credentials.get("token") or ""),
                str(credentials.get("base_url") or "").strip() or _GITHUB_API,
            )
            try:
                user = await client.get_user()
            finally:
                await client.close()
            login = user.get("login")
            return str(login) if isinstance(login, str) and login else None

        if provider is IntegrationProvider.JIRA:
            client = JiraClient(
                str(credentials.get("base_url") or ""),
                str(credentials.get("email") or ""),
                str(credentials.get("api_token") or ""),
            )
            try:
                account = await client.myself()
            finally:
                await client.close()
            for key in ("emailAddress", "displayName", "name"):
                value = account.get(key)
                if isinstance(value, str) and value:
                    return value
            return None

        if provider is IntegrationProvider.GOOGLE:
            client = GoogleClient(credentials)
            try:
                account = await client.account()
            finally:
                await client.close()
            email = account.get("email")
            return str(email) if isinstance(email, str) and email else None

        return None

    # ---- internals --------------------------------------------------------

    async def _refresh_resources(self, integration: Integration) -> Integration:
        """Re-read the provider's resource list, keeping the current selection."""
        selected = {resource.id for resource in integration.resources if resource.selected}
        try:
            resources = await self._load_resources(
                integration.provider, self._plain(integration)
            )
        except IntegrationError as exc:
            integration.status = IntegrationStatus.ERROR
            integration.error = exc.message
            integration.updated_at = utcnow()
            return await self._save(integration.organization_id, integration)

        integration.resources = [
            IntegrationResource(
                id=resource["id"],
                name=resource["name"],
                kind=resource.get("kind", "resource"),
                selected=resource["id"] in selected,
                meta=resource.get("meta", {}),
            )
            for resource in resources
        ]
        integration.status = IntegrationStatus.CONNECTED
        integration.error = None
        integration.updated_at = utcnow()
        return await self._save(integration.organization_id, integration)

    async def _load_resources(
        self, provider: IntegrationProvider, credentials: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if provider is IntegrationProvider.GITHUB:
            client = GitHubClient(
                str(credentials.get("token") or ""),
                str(credentials.get("base_url") or "").strip() or _GITHUB_API,
            )
            try:
                repos = await client.list_repositories(per_page=100)
            finally:
                await client.close()
            return [
                {
                    "id": str(repo.get("full_name") or ""),
                    "name": str(repo.get("name") or repo.get("full_name") or ""),
                    "kind": "repository",
                    "meta": {
                        "private": bool(repo.get("private")),
                        "language": repo.get("language"),
                        "description": repo.get("description"),
                        "default_branch": repo.get("default_branch"),
                    },
                }
                for repo in repos
                if repo.get("full_name")
            ]

        if provider is IntegrationProvider.JIRA:
            client = JiraClient(
                str(credentials.get("base_url") or ""),
                str(credentials.get("email") or ""),
                str(credentials.get("api_token") or ""),
            )
            try:
                projects = await client.list_projects()
            finally:
                await client.close()
            return [
                {
                    "id": str(project.get("key") or ""),
                    "name": str(project.get("name") or project.get("key") or ""),
                    "kind": "project",
                    "meta": {"project_type": _project_type(project)},
                }
                for project in projects
                if project.get("key")
            ]

        # Google exposes no selectable container: the connected account is the scope.
        return []

    async def _save(self, org_id: str, integration: Integration) -> Integration:
        document = integration.model_dump(mode="python")
        document["id"] = integration.id
        document["organization_id"] = org_id
        document["credentials"] = integration.credentials
        stored = await self.repo.save(Paths.integrations(org_id), document)
        return self._to_model(stored)

    async def _load(
        self, org_id: str, provider: IntegrationProvider | str
    ) -> dict[str, Any] | None:
        provider_id = (
            provider.value if isinstance(provider, IntegrationProvider) else str(provider)
        )
        return await self.repo.get(Paths.integrations(org_id), provider_id)

    async def _require(self, org_id: str, integration_id: str) -> Integration:
        row = await self.repo.get(Paths.integrations(org_id), integration_id)
        if row is None:
            raise NotFoundError("That connection no longer exists.")
        return self._to_model(row)

    async def _require_admin(self, org_id: str, principal: Principal) -> None:
        row = await self.repo.membership(org_id, principal.user_id)
        if row is None:
            raise PermissionDeniedError("You are not a member of this organization.")
        role = OrgRole(row.get("role") or OrgRole.MEMBER)
        if ROLE_RANK.get(role, 0) < ROLE_RANK[OrgRole.ADMIN]:
            raise PermissionDeniedError(
                "Only organization owners and admins can manage integrations."
            )

    def _to_model(self, row: dict[str, Any]) -> Integration:
        return Integration.model_validate(row)

    def _plain(self, integration: Integration) -> dict[str, Any]:
        """Decrypt one integration's stored credentials."""
        try:
            return unseal_credentials(integration.credentials)
        except Exception as exc:
            logger.warning(
                "could not unseal %s credentials for org %s",
                integration.provider.value,
                integration.organization_id,
            )
            raise IntegrationError(
                "This connection's saved credentials could not be read. "
                "Reconnect it and try again."
            ) from exc

    def _credentials_from_token(
        self, provider: IntegrationProvider, token: dict[str, Any]
    ) -> dict[str, Any]:
        access_token = str(token.get("access_token") or "")
        if not access_token:
            raise IntegrationError(
                f"{provider_display_name(provider)} didn't return an access token. "
                "Please try reconnecting."
            )
        if provider is IntegrationProvider.GITHUB:
            return {"token": access_token}

        expires_in = token.get("expires_in")
        expiry = ""
        if isinstance(expires_in, int | float):
            expiry = (utcnow() + timedelta(seconds=float(expires_in))).isoformat()
        return {
            "access_token": access_token,
            "refresh_token": str(token.get("refresh_token") or ""),
            "client_id": self.settings.google_oauth_client_id or "",
            "client_secret": self.settings.google_oauth_client_secret or "",
            "expiry": expiry,
        }

    async def _audit_connected(
        self, org_id: str, integration: Integration, actor: Principal | None
    ) -> None:
        account = f" as {integration.account}" if integration.account else ""
        await self.audit.record(
            org_id,
            AuditAction.INTEGRATION_CONNECTED,
            actor_type=ActorType.USER if actor else ActorType.SYSTEM,
            actor_id=actor.user_id if actor else None,
            actor_name=actor.display_name if actor else "Buttlr",
            summary=(
                f"Connected {provider_display_name(integration.provider)}{account}."
            ),
            target_type="integration",
            target_id=integration.id,
            metadata={
                "provider": integration.provider.value,
                "account": integration.account,
                "resources": len(integration.resources),
            },
        )


def _providers_for(buttlr: Buttlr) -> set[IntegrationProvider]:
    """Providers this Buttlr needs: its declared integrations plus its tools."""
    providers: set[IntegrationProvider] = set()
    for value in buttlr.integrations or []:
        try:
            providers.add(IntegrationProvider(value))
        except ValueError:
            logger.debug("ignoring unknown integration %r on a Buttlr", value)
    for tool in buttlr.tools or []:
        provider = TOOL_PROVIDERS.get(str(tool).split(".", 1)[0].strip().lower())
        if provider is not None:
            providers.add(provider)
    return providers


def _project_type(project: dict[str, Any]) -> str | None:
    value = project.get("projectType") or project.get("style")
    if isinstance(value, dict):
        name = value.get("name")
        return str(name) if isinstance(name, str) else None
    return str(value) if isinstance(value, str) else None


def _granted_scopes(token: dict[str, Any], requested: tuple[str, ...]) -> list[str]:
    granted = token.get("scope")
    if isinstance(granted, str) and granted.strip():
        return [scope for scope in granted.replace(",", " ").split() if scope]
    return list(requested)
