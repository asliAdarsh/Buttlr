"""Model providers a workspace can pick from, and the credentials behind them.

Credentials come from two places, in this order:

1. what the organization entered in the application (encrypted at rest), then
2. what the deployment defines in its environment.

Providers are constructed from a *copy* of the settings with the organization's values applied,
so nothing about the runtime's provider code has to know where a key came from. The deterministic
``heuristic`` provider is always available, which is what keeps Buttlr usable with no model
account at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.crypto import seal_credentials, unseal_credentials
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from app.core.logging import get_logger
from app.database.base import Store
from app.database.repository import Paths, Repository
from app.runtime.models.base import ModelProvider
from app.runtime.models.providers import build_providers
from app.runtime.models.router import ModelRouter
from app.schemas.auth import Principal
from app.schemas.enums import AuditAction, OrgRole
from app.schemas.models import ModelProviderEntry, ModelProviderUpdate
from app.services.audit import AuditService

logger = get_logger(__name__)


@dataclass(frozen=True)
class ProviderSpec:
    """How one provider is presented, and which settings carry its credentials."""

    provider: str
    name: str
    kind: str
    description: str
    requires_key: bool
    requires_base_url: bool
    #: settings field name -> source document field name
    api_key_field: str | None
    base_url_field: str | None
    model_field: str
    default_model: str
    docs_url: str | None = None
    note: str = ""


CATALOGUE: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        provider="openai",
        name="OpenAI",
        kind="cloud",
        description="GPT models from OpenAI, or any OpenAI-compatible endpoint you point at.",
        requires_key=True,
        requires_base_url=False,
        api_key_field="openai_api_key",
        base_url_field="openai_base_url",
        model_field="openai_default_model",
        default_model="gpt-4o-mini",
        docs_url="https://platform.openai.com/api-keys",
    ),
    ProviderSpec(
        provider="anthropic",
        name="Anthropic",
        kind="cloud",
        description="Claude models from Anthropic.",
        requires_key=True,
        requires_base_url=False,
        api_key_field="anthropic_api_key",
        base_url_field=None,
        model_field="anthropic_default_model",
        default_model="claude-3-5-sonnet-latest",
        docs_url="https://console.anthropic.com/settings/keys",
    ),
    ProviderSpec(
        provider="google",
        name="Google Gemini",
        kind="cloud",
        description="Gemini models from Google AI Studio.",
        requires_key=True,
        requires_base_url=False,
        api_key_field="google_api_key",
        base_url_field="google_base_url",
        model_field="google_default_model",
        default_model="gemini-3.8-flash",
        docs_url="https://aistudio.google.com/app/apikey",
    ),
    ProviderSpec(
        provider="ollama",
        name="Local model (Ollama)",
        kind="local",
        description=(
            "A model running on your own machine or network. Nothing leaves your infrastructure."
        ),
        requires_key=False,
        requires_base_url=True,
        api_key_field=None,
        base_url_field="ollama_base_url",
        model_field="ollama_default_model",
        default_model="qwen2.5:7b",
        docs_url="https://ollama.com/download",
        note="Give the address of the Ollama server, for example http://localhost:11434.",
    ),
    ProviderSpec(
        provider="heuristic",
        name="Built-in planner",
        kind="builtin",
        description=(
            "Buttlr's deterministic planner. No account, no network, always available — it is "
            "the fallback whenever nothing else answers."
        ),
        requires_key=False,
        requires_base_url=False,
        api_key_field=None,
        base_url_field=None,
        model_field="",
        default_model="heuristic",
    ),
)

SPECS: dict[str, ProviderSpec] = {spec.provider: spec for spec in CATALOGUE}
ROLE_RANK = {OrgRole.MEMBER: 0, OrgRole.ADMIN: 1, OrgRole.OWNER: 2}


class ModelRegistry:
    """Resolves which model providers a given organization can actually use."""

    def __init__(self, store: Store, settings: Settings, audit: AuditService) -> None:
        self.store = store
        self.repo = Repository(store)
        self.settings = settings
        self.audit = audit
        self._routers: dict[str, ModelRouter] = {}
        self._deployment = ModelRouter(build_providers(settings))

    # ---- reads ------------------------------------------------------------

    @property
    def deployment(self) -> ModelRouter:
        """The router built from the deployment's own configuration."""
        return self._deployment

    async def entries(self, organization_id: str) -> list[ModelProviderEntry]:
        """Every provider the workspace may choose, with where its credentials come from."""
        stored = await self._stored(organization_id)
        entries: list[ModelProviderEntry] = []
        for spec in CATALOGUE:
            entry = self._entry(spec, stored.get(spec.provider))
            if entry is not None:
                entries.append(entry)
        return entries

    async def selectable(self, organization_id: str) -> list[ModelProviderEntry]:
        """Only the providers that can actually answer right now."""
        router = await self.router(organization_id)
        available = set(await router.available_providers())
        return [entry for entry in await self.entries(organization_id) if entry.provider in available]

    async def router(self, organization_id: str) -> ModelRouter:
        """A router for this organization: its own credentials first, deployment second."""
        cached = self._routers.get(organization_id)
        if cached is not None:
            return cached
        stored = await self._stored(organization_id)
        overrides: dict[str, Any] = {}
        for provider, document in stored.items():
            spec = SPECS.get(provider)
            if spec is None:
                continue
            credentials = self._plain(document)
            if spec.api_key_field and credentials.get("api_key"):
                overrides[spec.api_key_field] = credentials["api_key"]
            if spec.base_url_field and credentials.get("base_url"):
                overrides[spec.base_url_field] = credentials["base_url"]
            if credentials.get("model"):
                overrides[spec.model_field] = credentials["model"]
        if not overrides:
            # Nothing of the workspace's own: the deployment router is exactly right.
            return self._deployment
        router = ModelRouter(build_providers(self.settings.model_copy(update=overrides)))
        self._routers[organization_id] = router
        return router

    async def available(self, organization_id: str) -> list[str]:
        return await (await self.router(organization_id)).available_providers()

    # ---- writes -----------------------------------------------------------

    async def set_provider(
        self,
        principal: Principal,
        organization_id: str,
        provider: str,
        payload: ModelProviderUpdate,
    ) -> ModelProviderEntry:
        """Store a workspace's credentials for one provider."""
        spec = SPECS.get(provider)
        if spec is None:
            raise NotFoundError(f"Unknown model provider '{provider}'.")
        if spec.kind == "builtin":
            raise ValidationError(
                f"{spec.name} needs no credentials — it is always available as a fallback."
            )
        await self._require_admin(organization_id, principal)

        existing = self._plain((await self._stored(organization_id)).get(provider) or {})
        api_key = (payload.api_key or "").strip() or str(existing.get("api_key") or "")
        base_url = (payload.base_url or "").strip() or str(existing.get("base_url") or "")
        model = (payload.model or "").strip() or str(existing.get("model") or "")

        if spec.requires_key and not api_key:
            raise ValidationError(f"Paste the API key for {spec.name}.")
        if spec.requires_base_url and not base_url:
            raise ValidationError(
                "Give the address of your local model server, for example http://localhost:11434."
            )
        if base_url and not base_url.startswith(("http://", "https://")):
            raise ValidationError("The endpoint must start with http:// or https://.")

        document: dict[str, Any] = {
            "id": provider,
            "organization_id": organization_id,
            "provider": provider,
            "base_url": base_url or None,
            "model": model or None,
            "updated_by": principal.user_id,
        }
        if api_key:
            document["api_key"] = seal_credentials({"api_key": api_key})["api_key"]
        await self.repo.save(Paths.model_providers(organization_id), document)
        self._invalidate(organization_id)

        await self.audit.record(
            organization_id,
            AuditAction.SETTINGS_UPDATED,
            actor_type="user",
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"Configured the {spec.name} model provider.",
            target_type="model_provider",
            target_id=provider,
            metadata={"provider": provider, "model": model or spec.default_model},
        )
        entry = self._entry(spec, await self.repo.get(Paths.model_providers(organization_id), provider))
        assert entry is not None
        return entry

    async def clear_provider(
        self, principal: Principal, organization_id: str, provider: str
    ) -> None:
        spec = SPECS.get(provider)
        if spec is None:
            raise NotFoundError(f"Unknown model provider '{provider}'.")
        await self._require_admin(organization_id, principal)
        await self.repo.delete(Paths.model_providers(organization_id), provider)
        self._invalidate(organization_id)
        await self.audit.record(
            organization_id,
            AuditAction.SETTINGS_UPDATED,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"Removed the workspace's {spec.name} credentials.",
            target_type="model_provider",
            target_id=provider,
        )

    # ---- internals --------------------------------------------------------

    def _entry(self, spec: ProviderSpec, document: dict[str, Any] | None) -> ModelProviderEntry | None:
        """One provider as the UI sees it — never including a secret."""
        stored = self._plain(document) if document else {}
        stored_key = str(stored.get("api_key") or "")
        stored_base = str(stored.get("base_url") or "")
        deployment_key = (
            str(getattr(self.settings, spec.api_key_field, None) or "")
            if spec.api_key_field
            else ""
        )
        deployment_base = (
            str(getattr(self.settings, spec.base_url_field, None) or "")
            if spec.base_url_field
            else ""
        )
        api_key = stored_key or deployment_key
        base_url = stored_base or deployment_base
        # Only claim the deployment configured this if it supplies what the provider needs.
        # A provider's default endpoint (Google's, for instance) is not a credential.
        deployment_supplies = bool(deployment_key) or (
            spec.requires_base_url and bool(deployment_base)
        )
        source: str | None = None
        if stored_key or stored_base:
            source = "workspace"
        elif deployment_supplies:
            source = "deployment"

        configured = bool(api_key) if spec.requires_key else True
        if spec.requires_base_url and not base_url:
            configured = False
        if spec.kind == "builtin":
            configured = True
            source = None

        return ModelProviderEntry(
            provider=spec.provider,
            name=spec.name,
            kind=spec.kind,
            description=spec.description,
            configured=configured,
            source=source,
            model=str(stored.get("model") or "") or getattr(self.settings, spec.model_field, None) or spec.default_model,
            base_url=base_url or None,
            requires_key=spec.requires_key,
            requires_base_url=spec.requires_base_url,
            docs_url=spec.docs_url,
            note=spec.note,
        )

    async def _stored(self, organization_id: str) -> dict[str, dict[str, Any]]:
        rows = await self.repo.list(Paths.model_providers(organization_id), order_by=None)
        return {str(row.get("provider")): row for row in rows if row.get("provider")}

    @staticmethod
    def _plain(document: dict[str, Any] | None) -> dict[str, Any]:
        if not document:
            return {}
        sealed = document.get("api_key")
        if not sealed:
            return {"base_url": document.get("base_url"), "model": document.get("model")}
        try:
            api_key = unseal_credentials({"api_key": sealed})["api_key"]
        except Exception:
            logger.warning("stored model provider key could not be decrypted")
            api_key = ""
        return {
            "api_key": api_key,
            "base_url": document.get("base_url"),
            "model": document.get("model"),
        }

    async def _require_admin(self, organization_id: str, principal: Principal) -> None:
        row = await self.repo.membership(organization_id, principal.user_id)
        if row is None:
            raise PermissionDeniedError("You are not a member of this organization.")
        role = OrgRole(row.get("role") or OrgRole.MEMBER)
        if ROLE_RANK.get(role, 0) < ROLE_RANK[OrgRole.ADMIN]:
            raise PermissionDeniedError(
                "Only organization owners and admins can configure the model providers."
            )

    def _invalidate(self, organization_id: str) -> None:
        self._routers.pop(organization_id, None)

    async def close(self) -> None:
        for router in self._routers.values():
            for provider in router.providers.values():
                await _close_provider(provider)
        self._routers.clear()


async def _close_provider(provider: ModelProvider) -> None:
    try:
        await provider.close()
    except Exception:
        logger.warning("could not close model provider %s", provider.id)
