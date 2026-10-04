"""Execution routes, including the live SSE stream."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.deps import ContainerDep, OrgContext, OrgDep
from app.core.errors import ButtlrError
from app.core.logging import get_logger
from app.schemas.common import Page
from app.schemas.enums import ExecutionStatus
from app.schemas.execution import Execution, ExecutionEvent, ExecutionSummary

logger = get_logger(__name__)

router = APIRouter(tags=["executions"])

TERMINAL = {
    ExecutionStatus.COMPLETED.value,
    ExecutionStatus.FAILED.value,
    ExecutionStatus.CANCELLED.value,
}


@router.get("/organizations/{organization_id}/executions", response_model=Page[ExecutionSummary])
async def list_executions(
    container: ContainerDep,
    ctx: OrgDep,
    buttlr_id: str | None = Query(default=None),
    status_filter: ExecutionStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[ExecutionSummary]:
    return await container.executions.list(
        ctx.organization.id,
        buttlr_id=buttlr_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/organizations/{organization_id}/executions/{execution_id}", response_model=Execution)
async def get_execution(container: ContainerDep, ctx: OrgDep, execution_id: str) -> Execution:
    execution = await container.executions.get(ctx.organization.id, execution_id)
    await _authorize_view(container, ctx, execution.buttlr_id)
    return execution


@router.post(
    "/organizations/{organization_id}/executions/{execution_id}/cancel", response_model=Execution
)
async def cancel_execution(
    container: ContainerDep, ctx: OrgDep, execution_id: str
) -> Execution:
    existing = await container.executions.get(ctx.organization.id, execution_id)
    await _authorize_view(container, ctx, existing.buttlr_id)
    return await container.executions.cancel(ctx.organization.id, execution_id)


def _format(event: ExecutionEvent) -> str:
    return f"event: message\ndata: {event.model_dump_json()}\n\n"


async def _authorize_view(container: ContainerDep, ctx: OrgContext, buttlr_id: str) -> None:
    """A run is only visible to someone who may view the Buttler that produced it."""
    await container.buttlrs.get(ctx.organization.id, buttlr_id, access=ctx.access)


@router.get("/organizations/{organization_id}/executions/{execution_id}/stream")
async def stream_execution(
    container: ContainerDep, ctx: OrgDep, execution_id: str
) -> StreamingResponse:
    execution = await container.executions.get(ctx.organization.id, execution_id)
    await _authorize_view(container, ctx, execution.buttlr_id)
    organization_id = ctx.organization.id

    async def event_stream():
        async with container.bus.subscribe(execution_id) as queue:
            for event in container.bus.history(execution_id):
                yield _format(event)
            current = execution
            if current.status.value in TERMINAL:
                yield _format(
                    ExecutionEvent(
                        execution_id=execution_id,
                        event="done",
                        status=current.status,
                        output=current.output,
                        error=current.error,
                    )
                )
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    try:
                        current = await container.executions.get(organization_id, execution_id)
                    except ButtlrError:
                        return
                    if current.status.value in TERMINAL:
                        yield _format(
                            ExecutionEvent(
                                execution_id=execution_id,
                                event="done",
                                status=current.status,
                                output=current.output,
                                error=current.error,
                            )
                        )
                        return
                    continue
                yield _format(event)
                if event.event == "status" and event.status and event.status.value in TERMINAL:
                    return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["TERMINAL", "router"]
