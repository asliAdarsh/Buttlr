"""Approval centre routes.

Deciding an approval is only half the story: a granted approval resumes the paused Buttlr run,
and a rejected one lets it continue with that action marked as refused.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep, OrgContext, OrgDep
from app.core.errors import ButtlrError
from app.core.logging import get_logger
from app.runtime.executor import ResumeJob
from app.schemas.approval import Approval, ApprovalDecision, ApprovalStats
from app.schemas.common import Page
from app.schemas.enums import ApprovalStatus, ExecutionStatus

logger = get_logger(__name__)

router = APIRouter(tags=["approvals"])


@router.get("/organizations/{organization_id}/approvals/stats", response_model=ApprovalStats)
async def approval_stats(container: ContainerDep, ctx: OrgDep) -> ApprovalStats:
    return await container.approvals.stats(ctx.organization.id)


@router.get("/organizations/{organization_id}/approvals", response_model=Page[Approval])
async def list_approvals(
    container: ContainerDep,
    ctx: OrgDep,
    status_filter: ApprovalStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[Approval]:
    return await container.approvals.list(
        ctx.organization.id, status=status_filter, limit=limit, offset=offset
    )


async def _resume(container: ContainerDep, ctx: OrgContext, approval: Approval, granted: bool) -> None:
    if approval.status not in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
        return
    try:
        buttlr = await container.buttlrs.get(ctx.organization.id, approval.buttlr_id)
        execution = await container.executions.get(ctx.organization.id, approval.execution_id)
    except ButtlrError as exc:
        logger.warning("cannot resume execution for approval %s: %s", approval.id, exc.message)
        return
    if execution.status != ExecutionStatus.WAITING_APPROVAL:
        return
    container.runner.submit_resume(
        ResumeJob(
            organization=ctx.organization,
            buttlr=buttlr,
            execution=execution,
            approval=approval,
            granted=granted,
            access=ctx.access,
        )
    )


@router.post(
    "/organizations/{organization_id}/approvals/{approval_id}/approve", response_model=Approval
)
async def approve(
    container: ContainerDep,
    ctx: OrgDep,
    approval_id: str,
    payload: ApprovalDecision | None = None,
) -> Approval:
    approval = await container.approvals.decide(
        ctx.principal, ctx.organization.id, approval_id, True, payload.note if payload else None
    )
    await _resume(container, ctx, approval, granted=True)
    return approval


@router.post(
    "/organizations/{organization_id}/approvals/{approval_id}/reject", response_model=Approval
)
async def reject(
    container: ContainerDep,
    ctx: OrgDep,
    approval_id: str,
    payload: ApprovalDecision | None = None,
) -> Approval:
    approval = await container.approvals.decide(
        ctx.principal, ctx.organization.id, approval_id, False, payload.note if payload else None
    )
    await _resume(container, ctx, approval, granted=False)
    return approval
