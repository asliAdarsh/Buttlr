"""Execution persistence and live progress publishing.

The executor drives an execution through :meth:`ExecutionService.set_status` and
:meth:`ExecutionService.append_step`; this service is the single writer that keeps the
stored document, the in-memory model and the SSE event stream in step with each other.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.database.base import Condition, Op, Sort, Store, new_id
from app.database.repository import Paths, Repository
from app.runtime.pubsub import ExecutionBus
from app.schemas.buttlr import Buttlr, ButtlrStats
from app.schemas.common import Page, utcnow
from app.schemas.enums import ActorType, AuditAction, ExecutionStatus, ExecutionTrigger
from app.schemas.execution import (
    Execution,
    ExecutionEvent,
    ExecutionStep,
    ExecutionSummary,
    to_summary,
)
from app.services.audit import AuditService

logger = get_logger(__name__)

CANCELLABLE: frozenset[ExecutionStatus] = frozenset(
    {
        ExecutionStatus.QUEUED,
        ExecutionStatus.RUNNING,
        ExecutionStatus.WAITING_APPROVAL,
    }
)

TERMINAL: frozenset[ExecutionStatus] = frozenset(
    {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}
)

_SUCCESS_STATUSES: frozenset[ExecutionStatus] = frozenset({ExecutionStatus.COMPLETED})

# ``set_status`` accepts these as keyword fields; anything else is rejected loudly rather
# than silently dropped.
_STATUS_FIELDS: frozenset[str] = frozenset(
    {
        "started_at",
        "finished_at",
        "duration_ms",
        "pending_approval_id",
        "error",
        "output",
        "usage",
    }
)


class ExecutionService:
    def __init__(self, store: Store, audit: AuditService, bus: ExecutionBus) -> None:
        self.store = store
        self.audit = audit
        self.bus = bus
        self.repo = Repository(store)

    # ---- reads ------------------------------------------------------------

    async def get(self, organization_id: str, execution_id: str) -> Execution:
        raw = await self.repo.get(Paths.executions(organization_id), execution_id)
        if raw is None:
            raise NotFoundError("That run no longer exists.")
        return Execution.model_validate(raw)

    async def list(
        self,
        organization_id: str,
        *,
        buttlr_id: str | None = None,
        status: ExecutionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[ExecutionSummary]:
        conditions: list[Condition] = []
        if buttlr_id is not None:
            conditions.append(Condition("buttlr_id", Op.EQ, buttlr_id))
        if status is not None:
            conditions.append(Condition("status", Op.EQ, ExecutionStatus(status).value))
        collection = Paths.executions(organization_id)
        total = await self.repo.count(collection, conditions)
        rows = await self.repo.list(
            collection,
            conditions=conditions,
            order_by="created_at",
            sort=Sort.DESC,
            limit=limit,
            offset=offset,
        )
        return Page[ExecutionSummary](
            items=[to_summary(Execution.model_validate(row)) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    # ---- writes -----------------------------------------------------------

    async def create(
        self,
        organization_id: str,
        buttlr: Buttlr,
        trigger: ExecutionTrigger,
        goal: str,
        requested_by: str | None = None,
        dry_run: bool = False,
        conversation_id: str | None = None,
    ) -> Execution:
        execution = Execution(
            id=new_id(),
            organization_id=organization_id,
            buttlr_id=buttlr.id,
            buttlr_name=buttlr.name,
            conversation_id=conversation_id,
            trigger=ExecutionTrigger(trigger),
            status=ExecutionStatus.QUEUED,
            goal=goal,
            model=f"{buttlr.model.provider}:{buttlr.model.name}",
            requested_by=requested_by,
            dry_run=dry_run,
        )
        await self._persist(execution)
        logger.info(
            "Execution %s queued for %s (%s)",
            execution.id,
            buttlr.name,
            execution.trigger.value,
        )
        return execution

    async def append_step(self, execution: Execution, step: ExecutionStep) -> Execution:
        if step.index < 0:
            step.index = len(execution.steps)
        if step.started_at is None:
            step.started_at = utcnow()
        execution.steps.append(step)
        await self._persist(execution)
        await self.bus.publish(
            ExecutionEvent(execution_id=execution.id, event="step", step=step)
        )
        return execution

    async def set_status(
        self, execution: Execution, status: ExecutionStatus, **fields: Any
    ) -> Execution:
        unknown = set(fields) - _STATUS_FIELDS
        if unknown:
            raise ValueError(f"Unsupported execution fields: {sorted(unknown)}")
        execution.status = ExecutionStatus(status)
        for name, value in fields.items():
            setattr(execution, name, value)
        await self._persist(execution)
        await self.bus.publish(
            ExecutionEvent(
                execution_id=execution.id,
                event="status",
                status=execution.status,
                output=execution.output,
                error=execution.error,
            )
        )
        return execution

    async def finish(
        self,
        execution: Execution,
        status: ExecutionStatus,
        output: str | None = None,
        error: str | None = None,
    ) -> Execution:
        execution = await self.set_status(
            execution,
            status,
            finished_at=utcnow(),
            output=output if output is not None else execution.output,
            error=error if error is not None else execution.error,
        )
        if execution.started_at is not None:
            execution.duration_ms = max(
                0, int((execution.finished_at - execution.started_at).total_seconds() * 1000)
            )
            await self._persist(execution)
        await self._update_buttlr_stats(execution)
        return execution

    async def cancel(self, organization_id: str, execution_id: str) -> Execution:
        execution = await self.get(organization_id, execution_id)
        if execution.status not in CANCELLABLE:
            raise ConflictError(f"This run has already finished ({execution.status.value}).")
        execution = await self.finish(execution, ExecutionStatus.CANCELLED)
        await self.audit.record(
            organization_id,
            AuditAction.EXECUTION_CANCELLED,
            actor_type=ActorType.USER,
            actor_id=execution.requested_by,
            summary=f"Cancelled the run of {execution.buttlr_name}.",
            target_type="execution",
            target_id=execution.id,
            buttlr_id=execution.buttlr_id,
            execution_id=execution.id,
        )
        return execution

    # ---- internals --------------------------------------------------------

    async def _persist(self, execution: Execution) -> None:
        await self.repo.save(
            Paths.executions(execution.organization_id), execution.model_dump(mode="python")
        )

    async def _update_buttlr_stats(self, execution: Execution) -> None:
        """Fold a terminal run into the parent Buttlr's ``stats`` document.

        Statistics are a convenience, never a correctness requirement: a Buttlr that has
        been deleted mid-run must not turn a finished execution into an error.
        """
        collection = Paths.buttlrs(execution.organization_id)
        try:
            raw = await self.repo.get(collection, execution.buttlr_id)
        except Exception:  # pragma: no cover - store-level failure
            logger.exception("Could not read stats for Buttlr %s", execution.buttlr_id)
            return
        if raw is None:
            return
        stats = ButtlrStats.model_validate(raw.get("stats") or {})
        stats.total_runs += 1
        if execution.status in _SUCCESS_STATUSES:
            stats.successful_runs += 1
        elif execution.status in TERMINAL:
            stats.failed_runs += 1
        stats.last_run_at = execution.finished_at or utcnow()
        stats.last_status = execution.status
        stats.last_duration_ms = execution.duration_ms
        if execution.status in _SUCCESS_STATUSES:
            minutes = (execution.duration_ms or 0) / 60_000
            stats.estimated_minutes_saved += max(1, round(minutes))
        try:
            await self.repo.patch(
                collection, execution.buttlr_id, {"stats": stats.model_dump(mode="python")}
            )
        except Exception:  # pragma: no cover - store-level failure
            logger.exception("Could not write stats for Buttlr %s", execution.buttlr_id)
