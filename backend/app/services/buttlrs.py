"""The Buttlr registry: configure, deploy and run an AI employee.

This service is the only place a Buttlr document is written. It enforces three things the
runtime then relies on:

* **Real capability only.** Every tool name a Buttlr carries must exist in the registry, so
  a configuration can never name a tool the executor cannot resolve.
* **Explicit authority.** Every action resolves the caller's ``AccessContext`` from their
  stored membership and is checked by the permission engine against the Buttlr's grants.
* **No cross-organization reads.** A Buttlr is only ever loaded through its organization's
  collection path, so a document belonging to another organization is simply not found.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings
from app.core.errors import ModelError, NotFoundError, PermissionDeniedError, ValidationError
from app.core.logging import get_logger
from app.database.base import Condition, Op, Sort, Store, new_id
from app.database.repository import Paths, Repository
from app.integrations.service import connection_doc_id
from app.runtime.drafting import heuristic_draft, heuristic_refine
from app.runtime.models.base import CompletionRequest, Message
from app.runtime.models.registry import ModelRegistry
from app.runtime.permissions.engine import AccessContext, engine
from app.runtime.prompt import build_draft_from_plan, build_draft_prompt
from app.runtime.pubsub import ExecutionBus
from app.runtime.tools.registry import ToolRegistry
from app.schemas.auth import Principal
from app.schemas.buttlr import (
    ApprovalPolicy,
    Buttlr,
    ButtlrCreate,
    ButtlrDraftRequest,
    ButtlrDraftResponse,
    ButtlrRefineRequest,
    ButtlrRunRequest,
    ButtlrStatus,
    ButtlrUpdate,
    ModelConfig,
    PermissionGrant,
    Schedule,
)
from app.schemas.common import utcnow
from app.schemas.enums import (
    AuditAction,
    ExecutionTrigger,
    GrantSubject,
    IntegrationProvider,
    IntegrationScope,
    IntegrationStatus,
    ModelProviderKind,
    Permission,
)
from app.schemas.execution import Execution
from app.schemas.integration import TOOL_PROVIDER_PREFIXES, Integration, canonical_providers
from app.schemas.organization import Member, Organization
from app.services.audit import AuditService
from app.services.executions import ExecutionService
from app.workers.runner import ExecutionJob, ExecutionRunner

logger = get_logger(__name__)

#: Temperature for the builder. Low: a configuration must be reproducible.
_DRAFT_TEMPERATURE = 0.2
_DRAFT_MAX_TOKENS = 4096


class ButtlrService:
    def __init__(
        self,
        *,
        store: Store,
        audit: AuditService,
        registry: ToolRegistry,
        models: ModelRegistry,
        runner: ExecutionRunner,
        bus: ExecutionBus,
        settings: Settings,
    ) -> None:
        self.store = store
        self.repo = Repository(store)
        self.audit = audit
        self.registry = registry
        self.models = models
        self.runner = runner
        self.bus = bus
        self.settings = settings
        self.executions = ExecutionService(store, audit, bus)

    # ---- reads ------------------------------------------------------------

    async def list(
        self,
        organization_id: str,
        *,
        team_id: str | None = None,
        status: ButtlrStatus | None = None,
        q: str | None = None,
        access: AccessContext | None = None,
    ) -> list[Buttlr]:
        """Newest first, optionally narrowed by team, status and free text.

        When ``access`` is given, a Buttlr the caller cannot view is not returned at all —
        grants are checked per Buttlr, so a member only ever sees what they may operate.
        """
        conditions: list[Condition] = []
        if team_id is not None:
            conditions.append(Condition("team_id", Op.EQ, team_id))
        if status is not None:
            conditions.append(Condition("status", Op.EQ, ButtlrStatus(status).value))
        rows = await self.repo.list(
            Paths.buttlrs(organization_id),
            conditions=conditions,
            order_by="created_at",
            sort=Sort.DESC,
        )
        results = [Buttlr.model_validate(row) for row in rows]
        if q:
            needle = q.strip().lower()
            if needle:
                results = [
                    b
                    for b in results
                    if needle in b.name.lower()
                    or needle in b.role.lower()
                    or needle in (b.description or "").lower()
                ]
        if access is not None:
            results = [
                b
                for b in results
                if engine.can(buttlr=b, access=access, permission=Permission.VIEW)
            ]
        return results

    async def get(
        self, organization_id: str, buttlr_id: str, *, access: AccessContext | None = None
    ) -> Buttlr:
        """Load a Buttlr from its own organization's collection.

        A Buttlr id belonging to a different organization is not found here — the path
        never reaches it — so existence is never leaked across tenants. When ``access`` is
        given, the caller must also hold view permission on the Buttlr itself.
        """
        raw = await self.repo.get(Paths.buttlrs(organization_id), buttlr_id)
        if raw is None:
            raise NotFoundError("Buttlr not found.")
        buttlr = Buttlr.model_validate(raw)
        if buttlr.organization_id != organization_id:
            raise NotFoundError("Buttlr not found.")
        if access is not None:
            engine.require(
                buttlr=buttlr,
                access=access,
                permission=Permission.VIEW,
                action="view this Buttlr",
            )
        return buttlr

    # ---- writes -----------------------------------------------------------

    async def create(
        self, principal: Principal, organization_id: str, payload: ButtlrCreate
    ) -> Buttlr:
        await self._require_membership(principal, organization_id)
        self._validate_tools(payload.tools)
        self._validate_integrations(payload.integrations)
        integrations = canonical_providers(payload.tools, payload.integrations)

        permissions = list(payload.permissions)
        if not permissions:
            # The creator must be able to operate what they created; without a grant a
            # plain member could build a Buttlr nobody could run.
            permissions = [
                PermissionGrant(
                    subject_type=GrantSubject.USER,
                    subject=principal.user_id,
                    permission=Permission.ADMIN,
                )
            ]

        now = utcnow()
        buttlr = Buttlr(
            id=new_id(),
            organization_id=organization_id,
            team_id=payload.team_id,
            name=payload.name,
            avatar=payload.avatar,
            role=payload.role,
            department=payload.department,
            description=payload.description,
            objective=payload.objective,
            responsibilities=payload.responsibilities,
            instructions=payload.instructions,
            model=payload.model or ModelConfig(),
            tools=payload.tools,
            integrations=integrations,
            scope=payload.scope,
            schedule=payload.schedule or Schedule(),
            status=ButtlrStatus.DRAFT,
            approval_policy=payload.approval_policy or ApprovalPolicy(),
            permissions=permissions,
            memory_enabled=payload.memory_enabled,
            created_by=principal.user_id,
            created_at=now,
            updated_at=now,
        )
        stored = await self.repo.save(
            Paths.buttlrs(organization_id), buttlr.model_dump(mode="python")
        )
        await self.audit.record(
            organization_id,
            AuditAction.BUTTLR_CREATED,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"{principal.display_name} created the Buttlr {buttlr.name}",
            target_type="buttlr",
            target_id=buttlr.id,
            buttlr_id=buttlr.id,
            metadata={"tools": buttlr.tools, "integrations": buttlr.integrations},
        )
        return Buttlr.model_validate(stored)

    async def update(
        self,
        principal: Principal,
        organization_id: str,
        buttlr_id: str,
        patch: ButtlrUpdate,
    ) -> Buttlr:
        current = await self.get(organization_id, buttlr_id)
        access = await self._access(principal, organization_id)
        engine.require(
            buttlr=current,
            access=access,
            permission=Permission.CONFIGURE,
            action="change this configuration",
        )

        changes = patch.model_dump(exclude_unset=True, mode="python")
        if "tools" in changes and changes["tools"] is not None:
            self._validate_tools(list(changes["tools"]))
        if "integrations" in changes and changes["integrations"] is not None:
            self._validate_integrations(list(changes["integrations"]))
        if "tools" in changes or "integrations" in changes:
            changes["integrations"] = canonical_providers(
                list(changes.get("tools") or current.tools),
                list(changes.get("integrations") or current.integrations),
            )

        updated = current.model_copy(update={**changes, "updated_at": utcnow()})
        stored = await self.repo.save(
            Paths.buttlrs(organization_id), updated.model_dump(mode="python")
        )
        await self.audit.record(
            organization_id,
            AuditAction.BUTTLR_UPDATED,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"{principal.display_name} updated the Buttlr {updated.name}",
            target_type="buttlr",
            target_id=updated.id,
            buttlr_id=updated.id,
            metadata={"fields": sorted(changes.keys())},
        )
        return Buttlr.model_validate(stored)

    async def delete(
        self, principal: Principal, organization_id: str, buttlr_id: str
    ) -> None:
        current = await self.get(organization_id, buttlr_id)
        access = await self._access(principal, organization_id)
        engine.require(
            buttlr=current,
            access=access,
            permission=Permission.CONFIGURE,
            action="delete this Buttlr",
        )
        await self.repo.delete(Paths.buttlrs(organization_id), buttlr_id)
        await self.audit.record(
            organization_id,
            AuditAction.BUTTLR_DELETED,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"{principal.display_name} deleted the Buttlr {current.name}",
            target_type="buttlr",
            target_id=buttlr_id,
            metadata={"name": current.name},
        )

    async def deploy(
        self, principal: Principal, organization_id: str, buttlr_id: str
    ) -> Buttlr:
        current = await self.get(organization_id, buttlr_id)
        access = await self._access(principal, organization_id)
        engine.require(
            buttlr=current,
            access=access,
            permission=Permission.CONFIGURE,
            action="deploy this Buttlr",
        )
        await self._require_integrations_connected(current)

        now = utcnow()
        updated = current.model_copy(
            update={"status": ButtlrStatus.ACTIVE, "deployed_at": now, "updated_at": now}
        )
        stored = await self.repo.save(
            Paths.buttlrs(organization_id), updated.model_dump(mode="python")
        )
        await self.audit.record(
            organization_id,
            AuditAction.BUTTLR_DEPLOYED,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"{principal.display_name} deployed the Buttlr {updated.name}",
            target_type="buttlr",
            target_id=updated.id,
            buttlr_id=updated.id,
            metadata={"tools": updated.tools},
        )
        return Buttlr.model_validate(stored)

    async def pause(
        self, principal: Principal, organization_id: str, buttlr_id: str
    ) -> Buttlr:
        current = await self.get(organization_id, buttlr_id)
        access = await self._access(principal, organization_id)
        engine.require(
            buttlr=current,
            access=access,
            permission=Permission.CONFIGURE,
            action="pause this Buttlr",
        )
        updated = current.model_copy(
            update={"status": ButtlrStatus.PAUSED, "updated_at": utcnow()}
        )
        stored = await self.repo.save(
            Paths.buttlrs(organization_id), updated.model_dump(mode="python")
        )
        await self.audit.record(
            organization_id,
            AuditAction.BUTTLR_PAUSED,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"{principal.display_name} paused the Buttlr {updated.name}",
            target_type="buttlr",
            target_id=updated.id,
            buttlr_id=updated.id,
        )
        return Buttlr.model_validate(stored)

    async def run(
        self,
        principal: Principal,
        organization_id: str,
        buttlr_id: str,
        request: ButtlrRunRequest,
    ) -> Execution:
        """Queue a run. A dry run changes nothing, so it needs only view permission."""
        buttlr = await self.get(organization_id, buttlr_id)
        access = await self._access(principal, organization_id)
        engine.require(
            buttlr=buttlr,
            access=access,
            permission=Permission.VIEW if request.dry_run else Permission.EXECUTE,
            action="test this Buttlr" if request.dry_run else "run this Buttlr",
        )
        organization = await self._organization(organization_id)

        goal = (request.input or "").strip() or buttlr.objective or buttlr.name
        execution = await self.executions.create(
            organization_id=organization_id,
            buttlr=buttlr,
            trigger=ExecutionTrigger.TEST if request.dry_run else ExecutionTrigger.MANUAL,
            goal=goal,
            requested_by=principal.user_id,
            dry_run=request.dry_run,
        )
        self.runner.submit(
            ExecutionJob(
                organization=organization,
                buttlr=buttlr,
                execution=execution,
                goal=goal,
                trigger=execution.trigger,
                requested_by=principal.user_id,
                access=access,
                dry_run=request.dry_run,
            )
        )
        return execution

    # ---- natural-language creation ----------------------------------------

    async def draft(
        self, principal: Principal, organization_id: str, request: ButtlrDraftRequest
    ) -> ButtlrDraftResponse:
        """Turn a plain-English job description into a complete configuration.

        The builder never dead-ends: if no model provider can answer, the deterministic
        heuristic builder produces a real, deployable configuration instead.
        """
        await self._require_membership(principal, organization_id)
        organization = await self._organization(organization_id)
        tool_names = self.registry.names()
        specs = self.registry.specs()
        context = await self._draft_context(organization, request.team_id)

        system, user = build_draft_prompt(
            request.prompt,
            specs,
            default_timezone=context["default_timezone"],
            teams=context["teams"],
            organization_name=organization.name,
        )

        try:
            router = await self.models.router(organization_id)
            if await router.available_providers() == [ModelProviderKind.HEURISTIC.value]:
                # Only the deterministic planner is configured. The explicit fallback below is
                # better than it: it receives the tool names structurally instead of guessing.
                raise ModelError("no language model is configured")
            # No function-calling tools on this call: the catalogue is described in the prompt,
            # and a provider offered callable tools answers with a tool call rather than the
            # configuration JSON we asked for.
            response = await router.complete(
                ModelConfig(provider="auto"),
                CompletionRequest(
                    messages=[Message(role="user", content=user)],
                    system=system,
                    json_mode=True,
                    temperature=_DRAFT_TEMPERATURE,
                    max_tokens=_DRAFT_MAX_TOKENS,
                ),
            )
            if response.provider == ModelProviderKind.HEURISTIC.value:
                raise ValueError("the deterministic planner answered instead of a model")
            plan = _parse_json_object(response.content)
        except (ModelError, ValidationError, ValueError) as exc:
            logger.info("draft fell back to the heuristic builder: %s", exc)
            return _response_from_plan(
                heuristic_draft(
                    request.prompt,
                    tool_names,
                    default_timezone=context["default_timezone"],
                    teams=context["teams"],
                    organization_name=organization.name,
                ),
                provider="heuristic",
                model="heuristic",
            )

        resolved = build_draft_from_plan(plan).model_copy(
            update={"team_id": request.team_id or plan.get("team_id")}
        )
        return _response_from_plan(
            plan,
            draft=resolved,
            provider=response.provider or "heuristic",
            model=response.model or "heuristic",
        )

    async def refine(
        self, principal: Principal, organization_id: str, request: ButtlrRefineRequest
    ) -> ButtlrDraftResponse:
        """Apply a follow-up instruction to an existing draft."""
        await self._require_membership(principal, organization_id)
        organization = await self._organization(organization_id)
        tool_names = self.registry.names()
        specs = self.registry.specs()
        context = await self._draft_context(organization, None)

        current = request.current.model_dump(mode="python")
        system, user = build_draft_prompt(
            _refine_request_text(request.instruction, current),
            specs,
            default_timezone=context["default_timezone"],
            teams=context["teams"],
            organization_name=organization.name,
        )

        # No tool catalogue is attached here: without a real language model the offline
        # provider cannot apply an instruction to an existing configuration, so it answers
        # in prose and the deterministic refiner below produces the result instead.
        try:
            router = await self.models.router(organization_id)
            available = await router.available_providers()
            if available == [ModelProviderKind.HEURISTIC.value]:
                raise ModelError("no language model is configured")
            response = await router.complete(
                ModelConfig(provider="auto"),
                CompletionRequest(
                    messages=[Message(role="user", content=user)],
                    system=system,
                    json_mode=True,
                    temperature=_DRAFT_TEMPERATURE,
                    max_tokens=_DRAFT_MAX_TOKENS,
                ),
            )
            if response.provider == ModelProviderKind.HEURISTIC.value:
                raise ValueError("the deterministic planner answered instead of a model")
            plan = _parse_json_object(response.content)
            resolved = build_draft_from_plan(plan)
            return _response_from_plan(
                plan,
                draft=resolved,
                provider=response.provider or "heuristic",
                model=response.model or "heuristic",
            )
        except (ModelError, ValidationError, ValueError) as exc:
            logger.info("refine fell back to the heuristic builder: %s", exc)
            return _response_from_plan(
                heuristic_refine(current, request.instruction, tool_names),
                provider="heuristic",
                model="heuristic",
            )

    # ---- validation -------------------------------------------------------

    def _validate_tools(self, tools: list[str]) -> None:
        """Reject a tool the registry cannot resolve — a typo here fails silently later."""
        known = set(self.registry.names())
        unknown = sorted({name for name in tools if name not in known})
        if unknown:
            raise ValidationError(
                f"Unknown tool{'s' if len(unknown) > 1 else ''}: {', '.join(unknown)}.",
                details={"unknown_tools": unknown, "available_tools": sorted(known)},
            )

    @staticmethod
    def _validate_integrations(integrations: list[str]) -> None:
        """Reject a connection name that belongs to neither a provider nor a tool family."""
        known = {provider.value for provider in IntegrationProvider} | set(TOOL_PROVIDER_PREFIXES)
        unknown = sorted({name for name in integrations if name not in known})
        if unknown:
            raise ValidationError(
                f"Unknown integration{'s' if len(unknown) > 1 else ''}: "
                f"{', '.join(unknown)}.",
                details={"unknown_integrations": unknown, "available": sorted(known)},
            )

    async def _require_integrations_connected(self, buttlr: Buttlr) -> None:
        """The deployment gate: every provider the Buttlr depends on must be reachable.

        Reachable means the workspace has connected it, or the person who owns the Buttlr
        connected their own account — the same resolution the runtime uses at run time.
        Configuration is permissive on purpose: a Buttlr may be drafted before its
        integrations exist, but deploying something that cannot reach its tools would be a
        lie, so it is refused here.
        """
        organization_id = buttlr.organization_id
        missing: list[str] = []
        for provider in dict.fromkeys(buttlr.integrations):
            if await self._reachable_integration(organization_id, provider, buttlr.created_by):
                continue
            missing.append(provider)
        if missing:
            raise ValidationError(
                f"Connect {missing[0]} in Integrations before deploying {buttlr.name}.",
                details={"missing_integrations": missing},
            )

    async def _reachable_integration(
        self, organization_id: str, provider: str, owner_id: str | None
    ) -> Integration | None:
        """The shared connection for a provider, or the owner's own. ``None`` when neither."""
        try:
            provider_kind = IntegrationProvider(provider)
        except ValueError:
            return None
        candidate_ids = [connection_doc_id(provider_kind, IntegrationScope.ORGANIZATION, None)]
        if owner_id:
            candidate_ids.insert(
                0, connection_doc_id(provider_kind, IntegrationScope.PERSONAL, owner_id)
            )
        for doc_id in candidate_ids:
            raw = await self.repo.get(Paths.integrations(organization_id), doc_id)
            if raw is None:
                continue
            integration = Integration.model_validate(raw)
            if integration.status == IntegrationStatus.CONNECTED:
                return integration
        return None

    async def _integration(
        self, organization_id: str, provider: str
    ) -> Integration | None:
        raw = await self.repo.get(Paths.integrations(organization_id), provider)
        return Integration.model_validate(raw) if raw else None

    # ---- access -----------------------------------------------------------

    async def _organization(self, organization_id: str) -> Organization:
        raw = await self.repo.get(Paths.ORGANIZATIONS, organization_id)
        if raw is None:
            raise NotFoundError("Organization not found.")
        return Organization.model_validate(raw)

    async def _member(self, principal: Principal, organization_id: str) -> Member:
        raw = await self.repo.membership(organization_id, principal.user_id)
        if raw is None:
            raise PermissionDeniedError("You are not a member of this organization.")
        return Member.model_validate(raw)

    async def _require_membership(
        self, principal: Principal, organization_id: str
    ) -> Member:
        await self._organization(organization_id)
        return await self._member(principal, organization_id)

    async def _access(self, principal: Principal, organization_id: str) -> AccessContext:
        """The only way an ``AccessContext`` is built: from the stored membership and the
        organization's own settings. Nothing is accepted from the request."""
        organization = await self._organization(organization_id)
        member = await self._member(principal, organization_id)
        return AccessContext(
            user_id=principal.user_id,
            org_role=member.role,
            team_ids=tuple(member.team_ids),
            settings=organization.settings,
        )

    async def _draft_context(
        self, organization: Organization, team_id: str | None
    ) -> dict[str, Any]:
        rows = await self.repo.list(
            Paths.teams(organization.id), order_by=None, sort=Sort.ASC
        )
        teams = [str(row.get("name") or row.get("id") or "") for row in rows]
        if team_id:
            teams = [team_id, *teams]
        return {
            "teams": teams,
            "default_timezone": getattr(organization.settings, "timezone", None)
            or self.settings.scheduler_timezone
            or "UTC",
        }


# ---- module helpers ----------------------------------------------------


def _strip_fences(text: str) -> str:
    """Models sometimes wrap JSON in ```json fences despite being told not to."""
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    lines = cleaned.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_json_object(content: str) -> dict[str, Any]:
    """Parse a model reply into a plan dict, or raise so the caller can fall back."""
    text = _strip_fences(content)
    if not text:
        raise ValueError("the model returned an empty response")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        # Some providers wrap the object in prose; take the outermost brace span.
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError(f"the model response was not JSON: {exc}") from exc
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("the model response was not a JSON object")
    return parsed


def _response_from_plan(
    plan: dict[str, Any],
    *,
    provider: str,
    model: str,
    draft: ButtlrCreate | None = None,
) -> ButtlrDraftResponse:
    resolved = draft or build_draft_from_plan(plan)
    rationale = plan.get("rationale")
    assumptions = plan.get("assumptions") or []
    missing = plan.get("missing") or []
    return ButtlrDraftResponse(
        draft=resolved,
        rationale=str(rationale or ""),
        assumptions=[str(item) for item in assumptions],
        missing=[str(item) for item in missing],
        provider=provider,
        model=model,
    )


def _refine_request_text(instruction: str, current: dict[str, Any]) -> str:
    """Frame the refine request: the current configuration, then the change to make."""
    return (
        "Revise the following Buttlr configuration according to the instruction. "
        "Return the complete configuration again with every key, changing only what the "
        "instruction asks for.\n\n"
        f"Instruction: {instruction.strip()}\n\n"
        f"Current configuration:\n{json.dumps(current, indent=2, default=str)}"
    )


__all__ = ["ButtlrService"]
