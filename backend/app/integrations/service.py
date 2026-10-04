"""Connections between an organization and the tools its Buttlrs use.

Anyone can connect **their own** account; an owner or admin can additionally connect a
**shared** account for the whole workspace. Both are stored encrypted at rest with
``app.core.crypto`` and never leave this module in plaintext: every public method returns a
``to_public()`` projection, and only :meth:`IntegrationService.credentials_for` hands
decrypted credentials out, keyed by provider.

A Buttlr runs with, in order of preference, the account of the person running it, the account
of the person who owns it, and finally the workspace's shared account. Nothing is read from
the environment.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.core.config import Settings
from app.core.crypto import mask_secret, seal_credentials, unseal_credentials
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
    deployment_client,
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
    IntegrationScope,
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
    OAuthClientPublic,
    OAuthClientUpdate,
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

    async def list(
        self, org_id: str, *, viewer_id: str, is_admin: bool = False
    ) -> list[IntegrationPublic]:
        """Connections this person may see.

        Everyone sees the workspace's shared connections and their own; administrators also
        see the personal connections they are responsible for.
        """
        rows = await self.repo.list(
            Paths.integrations(org_id), order_by="created_at", sort=Sort.DESC
        )
        visible: list[IntegrationPublic] = []
        for row in rows:
            integration = self._to_model(row)
            if (
                integration.scope is IntegrationScope.PERSONAL
                and not is_admin
                and integration.owner_id != viewer_id
            ):
                continue
            visible.append(integration.to_public())
        return visible

    async def get(
        self, org_id: str, provider: IntegrationProvider | str
    ) -> Integration | None:
        """The workspace's shared connection for a provider, if there is one."""
        row = await self._load(org_id, provider)
        return self._to_model(row) if row else None

    async def preferred(
        self,
        org_id: str,
        provider: IntegrationProvider,
        *,
        user_id: str | None = None,
        creator_id: str | None = None,
    ) -> Integration | None:
        """The connection a run by this person would use: theirs, the owner's, then shared."""
        by_key = await self._index(org_id)
        return self._preferred(by_key, provider, user_id, creator_id)

    async def credentials_for(
        self, org_id: str, buttlr: Buttlr, user_id: str | None = None
    ) -> dict[str, dict[str, Any]]:
        """Decrypted credentials for every provider this Buttlr can reach.

        Resolution order per provider: the account of the person running the Buttlr, then the
        account of the person who owns it, then the workspace's shared account. A provider
        with none of those contributes nothing, so its tool fails closed with its own
        actionable message.
        """
        wanted = _providers_for(buttlr)
        if not wanted:
            return {}
        by_key = await self._index(org_id)
        resolved: dict[str, dict[str, Any]] = {}
        for provider in sorted(wanted, key=lambda item: item.value):
            integration = self._preferred(by_key, provider, user_id, buttlr.created_by)
            if integration is None:
                continue
            try:
                resolved[provider.value] = unseal_credentials(integration.credentials)
            except Exception:
                logger.warning(
                    "could not unseal %s credentials for org %s",
                    provider.value,
                    org_id,
                )
        return resolved

    async def _index(
        self, org_id: str
    ) -> dict[tuple[IntegrationProvider, str | None], Integration]:
        """Stored connections keyed by (provider, owner) — ``owner`` is ``None`` when shared."""
        rows = await self.repo.list(Paths.integrations(org_id), order_by=None)
        index: dict[tuple[IntegrationProvider, str | None], Integration] = {}
        for row in rows:
            integration = self._to_model(row)
            owner = (
                integration.owner_id
                if integration.scope is IntegrationScope.PERSONAL
                else None
            )
            index[(integration.provider, owner)] = integration
        return index

    @staticmethod
    def _preferred(
        index: dict[tuple[IntegrationProvider, str | None], Integration],
        provider: IntegrationProvider,
        *owner_ids: str | None,
    ) -> Integration | None:
        for owner_id in owner_ids:
            if not owner_id:
                continue
            candidate = index.get((provider, owner_id))
            if candidate is not None and _usable(candidate):
                return candidate
        shared = index.get((provider, None))
        return shared if shared is not None and _usable(shared) else None

    # ---- token connections ------------------------------------------------

    async def connect_token(
        self, principal: Principal, org_id: str, payload: IntegrationConnectToken
    ) -> IntegrationPublic:
        """Connect GitHub or Jira with a personal access token / API token.

        Any member may connect their own account. Only an owner or admin may connect the
        shared account the whole workspace uses.
        """
        role = await self._require_member(org_id, principal)
        scope = payload.scope
        if scope is IntegrationScope.ORGANIZATION and ROLE_RANK.get(
            role, 0
        ) < ROLE_RANK[OrgRole.ADMIN]:
            raise PermissionDeniedError(
                "Only organization owners and admins can connect a shared account. "
                "Connect it for yourself instead."
            )
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
            id=_doc_id(provider, scope, principal.user_id),
            organization_id=org_id,
            provider=provider,
            display_name=payload.label or provider_display_name(provider),
            scope=scope,
            owner_id=principal.user_id if scope is IntegrationScope.PERSONAL else None,
            owner_name=principal.display_name if scope is IntegrationScope.PERSONAL else None,
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
        self,
        org_id: str,
        provider: IntegrationProvider,
        redirect_uri: str,
        *,
        user_id: str,
        scope: IntegrationScope = IntegrationScope.PERSONAL,
    ) -> OAuthStartResponse:
        """Build the provider consent URL and the signed state that binds it.

        The client is the workspace's own OAuth app when an admin registered one, and the
        deployment's app otherwise — either way, the user connects inside the application.
        """
        if not redirect_uri:
            raise ValidationError("A redirect URL is required to start the connection.")
        config = require_provider_config(
            provider, self.settings, await self._oauth_client(org_id, provider)
        )
        state = sign_state(
            provider,
            org_id,
            redirect_uri,
            self.settings.dev_auth_secret,
            user_id=user_id,
            scope=scope.value,
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

        scope = IntegrationScope(str(claims.get("scope") or IntegrationScope.PERSONAL.value))
        user_id = str(claims.get("user") or "")
        if scope is IntegrationScope.PERSONAL and not user_id:
            raise ValidationError(
                "This connection request is missing its owner. Please start again."
            )

        config = require_provider_config(
            provider, self.settings, await self._oauth_client(org_id, provider)
        )
        token = await exchange_code(config, code, redirect_uri)
        credentials = self._credentials_from_token(provider, token, config)
        account = await self.probe(provider, credentials)

        personal = scope is IntegrationScope.PERSONAL
        integration = Integration(
            id=_doc_id(provider, scope, user_id),
            organization_id=org_id,
            provider=provider,
            display_name=provider_display_name(provider),
            scope=scope,
            owner_id=user_id if personal else None,
            owner_name=await self._display_name(user_id) if personal else None,
            status=IntegrationStatus.CONNECTED,
            account=account,
            scopes=_granted_scopes(token, config.scopes),
            credentials=seal_credentials(credentials),
            created_by=user_id or None,
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
        integration = await self._require(org_id, integration_id)
        await self._require_manage(org_id, principal, integration)
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
        integration = await self._require(org_id, integration_id)
        await self._require_manage(org_id, principal, integration)
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
            metadata={
                "provider": integration.provider.value,
                "scope": integration.scope.value,
            },
        )

    async def refresh_resources(
        self, principal: Principal, org_id: str, integration_id: str
    ) -> IntegrationPublic:
        integration = await self._require(org_id, integration_id)
        await self._require_manage(org_id, principal, integration)
        return (await self._refresh_resources(integration)).to_public()

    # ---- workspace OAuth applications -------------------------------------
    #
    # A workspace can register its own OAuth app instead of relying on one the deployment
    # defines. The client secret is encrypted at rest and only ever leaves as a boolean.

    async def oauth_clients(self, org_id: str) -> list[OAuthClientPublic]:
        """Which OAuth apps are available here, and the redirect URI to register.

        Never returns a secret — only whether one is stored.
        """
        statuses: list[OAuthClientPublic] = []
        for provider in (IntegrationProvider.GITHUB, IntegrationProvider.GOOGLE):
            callback = self.callback_url(provider)
            row = await self.repo.get(Paths.oauth_apps(org_id), provider.value)
            if row is not None:
                client = self._plain_app(row)
                client_id = str(client.get("client_id") or "")
                statuses.append(
                    OAuthClientPublic(
                        provider=provider,
                        configured=bool(client_id and client.get("client_secret")),
                        client_id=client_id,
                        masked_client_id=mask_secret(client_id, visible=6),
                        has_secret=bool(client.get("client_secret")),
                        source="workspace",
                        redirect_uri=callback,
                    )
                )
                continue
            deployment_id, deployment_secret = deployment_client(provider, self.settings)
            statuses.append(
                OAuthClientPublic(
                    provider=provider,
                    configured=bool(deployment_id and deployment_secret),
                    client_id=None,
                    masked_client_id=mask_secret(deployment_id, visible=6) if deployment_id else None,
                    has_secret=bool(deployment_secret),
                    source="deployment" if deployment_id and deployment_secret else None,
                    redirect_uri=callback,
                )
            )
        return statuses

    def callback_url(self, provider: IntegrationProvider) -> str:
        """The redirect URI to register in the provider's OAuth app."""
        return (
            f"{self.settings.oauth_redirect_base_url}"
            f"/api/v1/integrations/oauth/{provider.value}/callback"
        )

    async def set_oauth_client(
        self,
        principal: Principal,
        org_id: str,
        provider: IntegrationProvider,
        payload: OAuthClientUpdate,
    ) -> OAuthClientPublic:
        """Store the workspace's own OAuth app for a provider."""
        await self._require_admin(org_id, principal)
        if provider not in (IntegrationProvider.GITHUB, IntegrationProvider.GOOGLE):
            raise ValidationError(
                f"{provider_display_name(provider)} connects with a token, not OAuth."
            )
        existing = await self.repo.get(Paths.oauth_apps(org_id), provider.value)
        secret = (payload.client_secret or "").strip()
        if not secret:
            secret = str(self._plain_app(existing).get("client_secret") or "") if existing else ""
        if not secret:
            raise ValidationError(
                "Enter the client secret from your OAuth app so Buttlr can complete sign-in."
            )
        await self.repo.save(
            Paths.oauth_apps(org_id),
            {
                "id": provider.value,
                "organization_id": org_id,
                "provider": provider.value,
                "client_id": payload.client_id.strip(),
                "client_secret": seal_credentials({"client_secret": secret})["client_secret"],
                "created_by": principal.user_id,
                "updated_at": utcnow(),
            },
        )
        await self.audit.record(
            org_id,
            AuditAction.SETTINGS_UPDATED,
            actor_type=ActorType.USER,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"Set the workspace's own {provider_display_name(provider)} OAuth app.",
            target_type="oauth_app",
            target_id=provider.value,
            metadata={"provider": provider.value},
        )
        statuses = await self.oauth_clients(org_id)
        return next(status for status in statuses if status.provider is provider)

    async def clear_oauth_client(
        self, principal: Principal, org_id: str, provider: IntegrationProvider
    ) -> None:
        await self._require_admin(org_id, principal)
        await self.repo.delete(Paths.oauth_apps(org_id), provider.value)

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

    async def _require_member(self, org_id: str, principal: Principal) -> OrgRole:
        row = await self.repo.membership(org_id, principal.user_id)
        if row is None:
            raise PermissionDeniedError("You are not a member of this organization.")
        return OrgRole(row.get("role") or OrgRole.MEMBER)

    async def _require_admin(self, org_id: str, principal: Principal) -> None:
        role = await self._require_member(org_id, principal)
        if ROLE_RANK.get(role, 0) < ROLE_RANK[OrgRole.ADMIN]:
            raise PermissionDeniedError(
                "Only organization owners and admins can manage the workspace's connections."
            )

    async def _require_manage(
        self, org_id: str, principal: Principal, integration: Integration
    ) -> None:
        """You may manage your own connection; only admins manage the shared ones."""
        if (
            integration.scope is IntegrationScope.PERSONAL
            and integration.owner_id == principal.user_id
        ):
            return
        await self._require_admin(org_id, principal)

    async def _display_name(self, user_id: str) -> str | None:
        row = await self.repo.get_user(user_id)
        name = (row or {}).get("display_name")
        return str(name) if name else None

    async def _oauth_client(
        self, org_id: str, provider: IntegrationProvider
    ) -> tuple[str | None, str | None] | None:
        """The workspace's own OAuth app, or ``None`` to fall back to the deployment's."""
        row = await self.repo.get(Paths.oauth_apps(org_id), provider.value)
        if row is None:
            return None
        client = self._plain_app(row)
        client_id = str(client.get("client_id") or "")
        client_secret = str(client.get("client_secret") or "")
        if not client_id or not client_secret:
            return None
        return (client_id, client_secret)

    @staticmethod
    def _plain_app(row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            return {}
        try:
            return unseal_credentials(
                {"client_secret": row.get("client_secret"), "client_id": row.get("client_id")}
            )
        except Exception:
            logger.warning("stored OAuth app credentials could not be decrypted")
            return {}

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
        self,
        provider: IntegrationProvider,
        token: dict[str, Any],
        config: Any | None = None,
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
        # The refresh needs the same client that obtained the token: the workspace's own app
        # when it has one, otherwise the deployment's.
        client_id = str(getattr(config, "client_id", "") or "") or (
            self.settings.google_oauth_client_id or ""
        )
        client_secret = str(getattr(config, "client_secret", "") or "") or (
            self.settings.google_oauth_client_secret or ""
        )
        return {
            "access_token": access_token,
            "refresh_token": str(token.get("refresh_token") or ""),
            "client_id": client_id,
            "client_secret": client_secret,
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
                "scope": integration.scope.value,
                "account": integration.account,
                "resources": len(integration.resources),
            },
        )


def connection_doc_id(
    provider: IntegrationProvider, scope: IntegrationScope, user_id: str | None
) -> str:
    """Document id for a connection: ``github`` shared, ``github:<user>`` personal."""
    if scope is IntegrationScope.PERSONAL and user_id:
        return f"{provider.value}:{user_id}"
    return provider.value


def _doc_id(
    provider: IntegrationProvider, scope: IntegrationScope, user_id: str | None
) -> str:
    return connection_doc_id(provider, scope, user_id)


def _usable(integration: Integration) -> bool:
    return integration.status not in _UNUSABLE_STATUSES and bool(integration.credentials)


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
