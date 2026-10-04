"""The Buttlr runtime loop.

    goal → planner → permission engine → tool execution → observation → planner → … → final

This module owns the loop, the pause for human approval, and the resume after a decision.
Every step it appends is a step that actually happened; the SSE stream and the audit trail
read from the same records.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.core.config import Settings
from app.core.errors import ButtlrError
from app.core.logging import get_logger
from app.database.base import Store, new_id
from app.database.repository import Paths, Repository
from app.integrations.service import IntegrationService
from app.runtime.memory import MemoryStoreService
from app.runtime.models.registry import ModelRegistry
from app.runtime.permissions.engine import AccessContext, PermissionEngine
from app.runtime.planner.base import (
    Observation,
    PlanAction,
    Planner,
    PlannerError,
    PlanRequest,
)
from app.runtime.planner.heuristic import HeuristicPlanner
from app.runtime.planner.llm import LLMPlanner
from app.runtime.prompt import build_system_prompt
from app.runtime.pubsub import ExecutionBus
from app.runtime.tools.base import Tool, ToolContext, ToolResult
from app.runtime.tools.registry import ToolRegistry
from app.schemas.activity import ChatMessage
from app.schemas.approval import Approval
from app.schemas.buttlr import Buttlr
from app.schemas.common import utcnow
from app.schemas.enums import (
    ActorType,
    AuditAction,
    ChatRole,
    ExecutionStatus,
    ExecutionTrigger,
    ModelProviderKind,
    NotificationKind,
    StepStatus,
    StepType,
)
from app.schemas.execution import Execution, ExecutionStep, Usage
from app.schemas.organization import Member, Organization
from app.services.approvals import ApprovalService
from app.services.audit import AuditService
from app.services.executions import ExecutionService
from app.services.notifications import NotificationService

logger = get_logger(__name__)


@dataclass
class ExecutionJob:
    organization: Organization
    buttlr: Buttlr
    execution: Execution
    goal: str
    trigger: ExecutionTrigger
    requested_by: str | None
    access: AccessContext
    dry_run: bool = False
    conversation_id: str | None = None


@dataclass
class ResumeJob:
    organization: Organization
    buttlr: Buttlr
    execution: Execution
    approval: Approval
    granted: bool
    access: AccessContext


@dataclass
class ExecutionOutcome:
    execution: Execution
    status: ExecutionStatus
    output: str | None = None
    pending_approval_id: str | None = None


TERMINAL_STATUSES = {
    ExecutionStatus.COMPLETED,
    ExecutionStatus.FAILED,
    ExecutionStatus.CANCELLED,
}


class ButtlrExecutor:
    def __init__(
        self,
        *,
        settings: Settings,
        store: Store,
        registry: ToolRegistry,
        models: ModelRegistry,
        permissions: PermissionEngine,
        executions: ExecutionService,
        approvals: ApprovalService,
        integrations: IntegrationService,
        audit: AuditService,
        notifications: NotificationService,
        bus: ExecutionBus,
    ) -> None:
        self.settings = settings
        self.store = store
        self.repo = Repository(store)
        self.registry = registry
        self.models = models
        self.permissions = permissions
        self.executions = executions
        self.approvals = approvals
        self.integrations = integrations
        self.audit = audit
        self.notifications = notifications
        self.bus = bus
        self.memory = MemoryStoreService(store)

    # ---- entry points -----------------------------------------------------

    async def run(self, job: ExecutionJob) -> Execution:
        execution = job.execution
        if execution.status == ExecutionStatus.CANCELLED:
            logger.info("execution %s was cancelled before it started", execution.id)
            return execution
        execution = await self.executions.set_status(
            execution, ExecutionStatus.RUNNING, started_at=execution.started_at or utcnow()
        )
        await self.audit.record(
            job.organization.id,
            AuditAction.EXECUTION_STARTED,
            actor_type=ActorType.BUTTLR,
            actor_id=job.buttlr.id,
            actor_name=job.buttlr.name,
            summary=f"{job.buttlr.name} started a run ({job.trigger.value}).",
            buttlr_id=job.buttlr.id,
            execution_id=execution.id,
            metadata={"trigger": job.trigger.value, "dry_run": job.dry_run},
        )
        return await self._drive(job, execution, observations=[])

    async def resume(self, job: ResumeJob) -> Execution:
        execution = job.execution
        execution = await self.executions.set_status(
            execution,
            ExecutionStatus.RUNNING,
            pending_approval_id=None,
            started_at=execution.started_at or utcnow(),
        )
        observations = self._observations_from_steps(execution)
        step_index = len(observations)
        execution = await self.executions.append_step(
            execution,
            ExecutionStep(
                index=step_index,
                type=StepType.APPROVAL_RESULT,
                title=(
                    f"Approved: {job.approval.action}"
                    if job.granted
                    else f"Rejected: {job.approval.action}"
                ),
                status=StepStatus.COMPLETED if job.granted else StepStatus.FAILED,
                detail=job.approval.decision_note or job.approval.reason,
                tool=job.approval.tool,
                params=job.approval.params,
                approval_id=job.approval.id,
                finished_at=utcnow(),
            ),
        )

        if job.granted:
            tool, ctx, _ = await self._prepare(job.organization, job.buttlr, execution, job.access)
            if tool is None:
                observations.append(
                    Observation(
                        tool=job.approval.tool,
                        arguments=job.approval.params,
                        ok=False,
                        summary="The requested tool is no longer available.",
                        approved=True,
                    )
                )
            else:
                result, execution = await self._execute_tool(
                    job, execution, tool, ctx, job.approval.params, step_index + 1
                )
                observations.append(self._observation(job.approval.tool, job.approval.params, result))
        else:
            observations.append(
                Observation(
                    tool=job.approval.tool,
                    arguments=job.approval.params,
                    ok=False,
                    summary=f"Rejected by a human reviewer: {job.approval.decision_note or 'no note'}",
                    approved=False,
                )
            )

        return await self._drive(job, execution, observations=observations)

    # ---- the loop ---------------------------------------------------------

    async def _drive(
        self,
        job: ExecutionJob | ResumeJob,
        execution: Execution,
        *,
        observations: list[Observation],
    ) -> Execution:
        shared = job if isinstance(job, ExecutionJob) else _as_job(job)
        try:
            tool, ctx, specs = await self._prepare(
                shared.organization, shared.buttlr, execution, shared.access
            )
        except ButtlrError as exc:
            return await self._fail(job, execution, str(exc.message))

        planner = await self._select_planner(shared.organization.id, shared.buttlr)
        system_prompt = build_system_prompt(shared.buttlr, specs, is_dry_run=shared.dry_run)
        if shared.buttlr.memory_enabled:
            block = await self.memory.as_prompt_block(shared.organization.id, shared.buttlr.id)
            if block:
                system_prompt = f"{system_prompt}\n\n{block}"

        if not specs:
            summary = (
                f"{shared.buttlr.name} has no tools configured, so there was nothing it could do. "
                "Add at least one tool in the Buttler configuration."
            )
            execution = await self.executions.append_step(
                execution, _message_step(len(observations), summary, StepStatus.FAILED)
            )
            return await self._finalize(
                job, execution, ExecutionStatus.FAILED, summary, summary, Usage()
            )

        usage = execution.usage
        model_label: str | None = execution.model
        provider_label: str | None = execution.provider
        output: str | None = None
        degraded: str | None = None
        #: (tool, arguments) pairs already run in this execution — including the ones carried
        #: over when a resume continues a paused run.
        attempted: set[tuple[str, str]] = {
            _call_signature(observation.tool, observation.arguments)
            for observation in observations
            if observation.tool
        }
        approvals_taken = sum(
            1 for step in execution.steps if step.type == StepType.APPROVAL_REQUEST
        )

        for _ in range(self.settings.max_agent_steps):
            fresh = await self._reload(execution)
            if fresh is not None:
                execution = fresh
            if execution.status == ExecutionStatus.CANCELLED:
                return execution

            request = PlanRequest(
                goal=shared.goal,
                system_prompt=system_prompt,
                tools=specs,
                observations=_trim_observations(observations, self.settings.max_observation_chars),
                step_index=len(observations),
                max_steps=self.settings.max_agent_steps,
                scope=shared.buttlr.scope,
            )
            try:
                plan = await planner.next(request)
            except PlannerError as exc:
                logger.warning("planner failed, falling back to heuristic: %s", exc)
                if not degraded:
                    last_error = planner.last_error if isinstance(planner, LLMPlanner) else None
                    degraded = str(last_error or exc)
                    execution = await self.executions.append_step(
                        execution,
                        ExecutionStep(
                            index=len(observations),
                            type=StepType.STATUS,
                            title="A configured model did not answer — continuing with the "
                            "built-in planner",
                            status=StepStatus.COMPLETED,
                            detail=degraded[:600],
                            finished_at=utcnow(),
                        ),
                    )
                planner = HeuristicPlanner()
                plan = await planner.next(request)

            usage = usage.add(plan.usage)
            if plan.provider:
                provider_label = plan.provider
            if plan.model:
                model_label = plan.model

            if plan.thought:
                execution = await self.executions.append_step(
                    execution,
                    ExecutionStep(
                        index=len(observations),
                        type=StepType.THINKING,
                        title=plan.thought[:280],
                        status=StepStatus.COMPLETED,
                    ),
                )

            if plan.action == PlanAction.FINAL:
                output = plan.final or "The run finished."
                execution = await self.executions.append_step(
                    execution, _message_step(len(observations), output)
                )
                return await self._finalize(
                    job,
                    execution,
                    ExecutionStatus.COMPLETED,
                    output,
                    None,
                    usage,
                    model=model_label,
                    provider=provider_label,
                )

            name = plan.tool or ""
            tool = self.registry.get(name)
            if tool is None:
                observations.append(
                    Observation(
                        tool=name,
                        arguments=plan.arguments,
                        ok=False,
                        summary=f"Tool '{name}' does not exist.",
                    )
                )
                continue

            signature = _call_signature(tool.name, plan.arguments)
            if signature in attempted:
                # A weak or offline model will happily re-issue a call it already made,
                # especially after an approval resumes the run. Re-running it would ask for
                # approval again and never progress, so record it and move on.
                observations.append(
                    Observation(
                        tool=tool.name,
                        arguments=plan.arguments,
                        ok=False,
                        summary=(
                            f"{tool.action_label()} was already run with these arguments in "
                            "this run; its result is above."
                        ),
                    )
                )
                execution = await self.executions.append_step(
                    execution,
                    ExecutionStep(
                        index=len(observations),
                        type=StepType.STATUS,
                        title=f"Skipped a repeated {tool.action_label()} call",
                        status=StepStatus.SKIPPED,
                        detail="Already run with the same arguments earlier in this run.",
                        tool=tool.name,
                        params=plan.arguments,
                        finished_at=utcnow(),
                    ),
                )
                continue
            attempted.add(signature)

            decision = self.permissions.evaluate(
                buttlr=shared.buttlr,
                access=shared.access,
                tool_name=tool.name,
                required_permission=tool.required_permission,
                risk=tool.risk,
                read_only=tool.read_only,
                owner_access=await self._owner_access(shared.organization, shared.buttlr, shared.access),
            )

            if decision.denied:
                execution = await self.executions.append_step(
                    execution,
                    ExecutionStep(
                        index=len(observations),
                        type=StepType.TOOL_CALL,
                        title=f"Blocked: {tool.action_label()}",
                        status=StepStatus.BLOCKED,
                        detail=decision.reason,
                        tool=tool.name,
                        params=plan.arguments,
                        finished_at=utcnow(),
                    ),
                )
                await self.audit.record(
                    shared.organization.id,
                    AuditAction.TOOL_DENIED,
                    actor_type=ActorType.BUTTLR,
                    actor_id=shared.buttlr.id,
                    actor_name=shared.buttlr.name,
                    summary=f"{shared.buttlr.name} was blocked from {tool.name}: {decision.reason}",
                    buttlr_id=shared.buttlr.id,
                    execution_id=execution.id,
                    metadata=decision.as_dict(),
                )
                observations.append(
                    Observation(
                        tool=tool.name, arguments=plan.arguments, ok=False, summary=decision.reason
                    )
                )
                continue

            if decision.requires_approval and not shared.dry_run:
                if approvals_taken >= self.settings.max_approvals_per_run:
                    summary = (
                        f"{shared.buttlr.name} asked for approval {approvals_taken} times in one "
                        "run and stopped there. Check the approval policy — a rule may be asking "
                        "before an action that does not need it."
                    )
                    execution = await self.executions.append_step(
                        execution, _message_step(len(observations), summary, StepStatus.FAILED)
                    )
                    return await self._finalize(
                        job,
                        execution,
                        ExecutionStatus.COMPLETED,
                        summary,
                        None,
                        usage,
                        model=model_label,
                        provider=provider_label,
                    )
                approvals_taken += 1
                approval = await self.approvals.create(
                    organization=shared.organization,
                    buttlr=shared.buttlr,
                    execution=execution,
                    step_index=len(observations),
                    decision=decision,
                    action=tool.action_label(),
                    resource=_resource_label(tool.name, plan.arguments),
                    reason=decision.reason,
                    params=plan.arguments,
                )
                execution = await self.executions.append_step(
                    execution,
                    ExecutionStep(
                        index=len(observations),
                        type=StepType.APPROVAL_REQUEST,
                        title=f"Approval required: {tool.action_label()}",
                        status=StepStatus.PENDING,
                        detail=decision.reason,
                        tool=tool.name,
                        params=plan.arguments,
                        approval_id=approval.id,
                    ),
                )
                execution = await self.executions.set_status(
                    execution,
                    ExecutionStatus.WAITING_APPROVAL,
                    pending_approval_id=approval.id,
                    usage=usage,
                )
                await self._persist_model_labels(execution, model_label, provider_label)
                return execution

            result, execution = await self._execute_tool(
                shared, execution, tool, ctx, plan.arguments, len(observations)
            )
            observations.append(self._observation(tool.name, plan.arguments, result))

        summary = output or (
            "The run reached its step limit before finishing. Review the steps above for progress."
        )
        execution = await self.executions.append_step(
            execution, _message_step(len(observations), summary, StepStatus.FAILED)
        )
        return await self._finalize(
            job,
            execution,
            ExecutionStatus.COMPLETED,
            summary,
            None,
            usage,
            model=model_label,
            provider=provider_label,
        )

    # ---- helpers ----------------------------------------------------------

    async def _prepare(
        self, organization: Organization, buttlr: Buttlr, execution: Execution, access: AccessContext
    ) -> tuple[Tool | None, ToolContext, list[Any]]:
        try:
            credentials = await self.integrations.credentials_for(
                organization.id, buttlr, access.user_id
            )
        except ButtlrError as exc:
            logger.warning("credential resolution failed: %s", exc.message)
            credentials = {}
        specs = self.registry.specs(buttlr.tools)
        ctx = ToolContext(
            organization_id=organization.id,
            buttlr_id=buttlr.id,
            execution_id=execution.id,
            user_id=access.user_id,
            scope=buttlr.scope,
            credentials=credentials,
            dry_run=execution.dry_run,
        )
        first = self.registry.resolve(buttlr.tools)
        return (first[0] if first else None), ctx, specs

    async def _select_planner(self, organization_id: str, buttlr: Buttlr) -> Planner:
        if buttlr.model.provider == ModelProviderKind.HEURISTIC.value:
            return HeuristicPlanner()
        try:
            router = await self.models.router(organization_id)
            available = [
                provider
                for provider in await router.available_providers()
                if provider != ModelProviderKind.HEURISTIC.value
            ]
        except Exception:
            router = self.models.deployment
            available = []
        if available:
            return LLMPlanner(router, buttlr.model)
        return HeuristicPlanner()

    async def _owner_access(
        self, organization: Organization, buttlr: Buttlr, access: AccessContext
    ) -> AccessContext | None:
        if not buttlr.created_by or buttlr.created_by == access.user_id:
            return None
        raw = await self.repo.get(Paths.members(organization.id), buttlr.created_by)
        if raw is None:
            return None
        try:
            member = Member.model_validate(raw)
        except PydanticValidationError:
            return None
        return AccessContext(
            user_id=member.user_id,
            org_role=member.role,
            team_ids=tuple(member.team_ids),
            settings=organization.settings,
        )

    async def _execute_tool(
        self,
        shared: ExecutionJob | ResumeJob,
        execution: Execution,
        tool: Tool,
        ctx: ToolContext,
        arguments: dict[str, Any],
        index: int,
    ) -> tuple[ToolResult, Execution]:
        try:
            params = tool.input_model.model_validate(arguments)
        except PydanticValidationError as exc:
            message = f"{tool.action_label()} was called with invalid arguments: {exc.errors()[:2]}"
            result = ToolResult.failure(message)
            execution = await self.executions.append_step(
                execution,
                ExecutionStep(
                    index=index,
                    type=StepType.TOOL_RESULT,
                    title=f"{tool.action_label()} failed",
                    status=StepStatus.FAILED,
                    detail=message,
                    tool=tool.name,
                    params=arguments,
                    finished_at=utcnow(),
                ),
            )
            return result, execution

        running = ExecutionStep(
            index=index,
            type=StepType.TOOL_CALL,
            title=f"Running {tool.action_label()}",
            status=StepStatus.RUNNING,
            tool=tool.name,
            params=_safe_params(params),
            started_at=utcnow(),
        )
        execution = await self.executions.append_step(execution, running)
        started = utcnow()

        try:
            result = await asyncio.wait_for(
                tool.run(ctx, params), timeout=self.settings.tool_timeout_seconds
            )
        except TimeoutError:
            result = ToolResult.failure(
                f"{tool.action_label()} timed out after {self.settings.tool_timeout_seconds:.0f}s."
            )
        except ButtlrError as exc:
            result = ToolResult.failure(exc.message)
        except Exception:
            logger.exception("tool %s crashed", tool.name)
            result = ToolResult.failure(f"{tool.action_label()} failed unexpectedly.")

        finished = utcnow()
        duration = int((finished - started).total_seconds() * 1000)
        execution = await self.executions.append_step(
            execution,
            ExecutionStep(
                index=index + 1,
                type=StepType.TOOL_RESULT,
                title=result.summary or tool.action_label(),
                status=StepStatus.COMPLETED if result.ok else StepStatus.FAILED,
                detail=result.error,
                tool=tool.name,
                params=_safe_params(params),
                result={"ok": result.ok, "summary": result.summary, "data": result.data},
                started_at=started,
                finished_at=finished,
                duration_ms=duration,
            ),
        )
        await self.audit.record(
            shared.organization.id,
            AuditAction.TOOL_EXECUTED,
            actor_type=ActorType.BUTTLR,
            actor_id=shared.buttlr.id,
            actor_name=shared.buttlr.name,
            summary=f"{shared.buttlr.name} ran {tool.name}: {result.summary}",
            buttlr_id=shared.buttlr.id,
            execution_id=execution.id,
            metadata={"tool": tool.name, "ok": result.ok, "dry_run": ctx.dry_run},
        )
        return result, execution

    @staticmethod
    def _observation(tool: str, arguments: dict[str, Any], result: ToolResult) -> Observation:
        return Observation(
            tool=tool,
            arguments=_json_safe(arguments),
            ok=result.ok,
            summary=result.summary,
            data=_json_safe(result.data),
        )

    @staticmethod
    def _observations_from_steps(execution: Execution) -> list[Observation]:
        observations: list[Observation] = []
        for step in execution.steps:
            if step.type == StepType.TOOL_RESULT and step.tool:
                payload = step.result or {}
                observations.append(
                    Observation(
                        tool=step.tool,
                        arguments=step.params or {},
                        ok=bool(payload.get("ok", step.status != StepStatus.FAILED)),
                        summary=payload.get("summary") or step.title,
                        data=payload.get("data"),
                    )
                )
            elif step.type == StepType.APPROVAL_RESULT and step.tool:
                approved = step.status == StepStatus.COMPLETED
                observations.append(
                    Observation(
                        tool=step.tool,
                        arguments=step.params or {},
                        ok=approved,
                        summary=step.title,
                        approved=approved,
                    )
                )
        return observations

    async def _persist_model_labels(
        self, execution: Execution, model: str | None, provider: str | None
    ) -> None:
        if not model and not provider:
            return
        execution.model = model or execution.model
        execution.provider = provider or execution.provider
        try:
            await self.repo.patch(
                Paths.executions(execution.organization_id),
                execution.id,
                {"model": execution.model, "provider": execution.provider},
            )
        except ButtlrError:  # pragma: no cover - bookkeeping must not fail a run
            logger.warning("could not persist model labels for execution %s", execution.id)

    async def _reload(self, execution: Execution) -> Execution | None:
        try:
            return await self.executions.get(execution.organization_id, execution.id)
        except ButtlrError:
            return None

    async def _fail(
        self, job: ExecutionJob | ResumeJob, execution: Execution, message: str
    ) -> Execution:
        execution = await self.executions.append_step(
            execution,
            ExecutionStep(
                index=len(execution.steps),
                type=StepType.ERROR,
                title=message,
                status=StepStatus.FAILED,
                finished_at=utcnow(),
            ),
        )
        return await self._finalize(job, execution, ExecutionStatus.FAILED, None, message, Usage())

    async def _finalize(
        self,
        job: ExecutionJob | ResumeJob,
        execution: Execution,
        status: ExecutionStatus,
        output: str | None,
        error: str | None,
        usage: Usage,
        *,
        model: str | None = None,
        provider: str | None = None,
    ) -> Execution:
        organization = job.organization
        buttlr = job.buttlr
        execution = await self.executions.finish(execution, status, output=output, error=error)
        if usage.calls or usage.total_tokens:
            execution.usage = usage
        if model:
            execution.model = model
        if provider:
            execution.provider = provider
        try:
            await self.repo.patch(
                Paths.executions(organization.id),
                execution.id,
                {
                    "usage": usage.model_dump(mode="python"),
                    "model": execution.model,
                    "provider": execution.provider,
                },
            )
        except ButtlrError:  # pragma: no cover - bookkeeping must not fail a run
            logger.warning("could not persist usage for execution %s", execution.id)

        if buttlr.memory_enabled and status == ExecutionStatus.COMPLETED and output:
            try:
                await self.memory.remember(
                    organization.id,
                    buttlr.id,
                    key=f"run:{execution.id}",
                    value=output[:1500],
                    kind="run_summary",
                )
            except ButtlrError:  # pragma: no cover
                logger.warning("memory write failed for %s", buttlr.id)

        await self.audit.record(
            organization.id,
            AuditAction.EXECUTION_COMPLETED
            if status == ExecutionStatus.COMPLETED
            else AuditAction.EXECUTION_FAILED,
            actor_type=ActorType.BUTTLR,
            actor_id=buttlr.id,
            actor_name=buttlr.name,
            summary=f"{buttlr.name} finished ({status.value}).",
            buttlr_id=buttlr.id,
            execution_id=execution.id,
            metadata={"status": status.value, "tokens": usage.total_tokens},
        )
        await self.notifications.notify(
            organization.id,
            NotificationKind.EXECUTION_COMPLETED
            if status == ExecutionStatus.COMPLETED
            else NotificationKind.EXECUTION_FAILED,
            title=f"{buttlr.name} {'completed a run' if status == ExecutionStatus.COMPLETED else 'failed a run'}",
            body=(output or error or "")[:280],
            link=f"/buttlrs/{buttlr.id}/runs/{execution.id}",
        )
        await self._write_chat_reply(job, execution, status, output, error)
        return execution

    async def _write_chat_reply(
        self,
        job: ExecutionJob | ResumeJob,
        execution: Execution,
        status: ExecutionStatus,
        output: str | None,
        error: str | None,
    ) -> None:
        conversation_id = execution.conversation_id
        if not conversation_id:
            return
        content = output or error or "The run finished without a result."
        message = ChatMessage(
            id=new_id(),
            organization_id=execution.organization_id,
            buttlr_id=execution.buttlr_id,
            conversation_id=conversation_id,
            role=ChatRole.ASSISTANT,
            content=content,
            execution_id=execution.id,
        )
        try:
            await self.repo.save(
                Paths.messages(execution.organization_id, execution.buttlr_id, conversation_id),
                message.model_dump(mode="python"),
            )
            collection = Paths.conversations(execution.organization_id, execution.buttlr_id)
            raw = await self.repo.get(collection, conversation_id)
            if raw:
                await self.repo.patch(
                    collection,
                    conversation_id,
                    {
                        "message_count": int(raw.get("message_count", 0)) + 1,
                        "updated_at": utcnow(),
                    },
                )
        except ButtlrError:  # pragma: no cover - chat bookkeeping must not fail a run
            logger.warning("could not persist chat reply for execution %s", execution.id)


def _as_job(job: ResumeJob) -> ExecutionJob:
    return ExecutionJob(
        organization=job.organization,
        buttlr=job.buttlr,
        execution=job.execution,
        goal=job.execution.goal,
        trigger=job.execution.trigger,
        requested_by=job.execution.requested_by,
        access=job.access,
        dry_run=job.execution.dry_run,
        conversation_id=job.execution.conversation_id,
    )


def _message_step(index: int, text: str, status: StepStatus = StepStatus.COMPLETED) -> ExecutionStep:
    return ExecutionStep(
        index=index,
        type=StepType.MESSAGE,
        title=text[:280],
        status=status,
        detail=text,
        finished_at=utcnow(),
    )


def _call_signature(tool: str, arguments: dict[str, Any]) -> tuple[str, str]:
    """Identity of a call, so the same one is never run twice in a single execution."""
    try:
        encoded = json.dumps(arguments, sort_keys=True, default=str)
    except (TypeError, ValueError):
        encoded = str(arguments)
    return (tool, encoded)


def _resource_label(tool: str, arguments: dict[str, Any]) -> str | None:
    for key in ("repository", "project", "spreadsheet_id", "document_id", "file_id", "to", "key"):
        value = arguments.get(key)
        if value:
            return f"{key}={value}"
    return None


def _safe_params(params: Any) -> dict[str, Any]:
    if hasattr(params, "model_dump"):
        return _json_safe(params.model_dump(mode="python"))
    return _json_safe(dict(params))


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, default=str)
        return value
    except (TypeError, ValueError):
        return json.loads(json.dumps(value, default=str))


def _trim_observations(observations: list[Observation], limit: int) -> list[Observation]:
    if not observations:
        return []
    trimmed: list[Observation] = []
    for observation in observations[-8:]:
        summary = observation.summary
        if len(summary) > limit:
            summary = summary[:limit] + "…"
        trimmed.append(observation.model_copy(update={"summary": summary, "data": None}))
    return trimmed
