"""Executions and their steps."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import DomainModel, utcnow
from app.schemas.enums import ExecutionStatus, ExecutionTrigger, StepStatus, StepType


class Usage(DomainModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    calls: int = 0

    def add(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            estimated_cost_usd=round(self.estimated_cost_usd + other.estimated_cost_usd, 6),
            calls=self.calls + other.calls,
        )


class ExecutionStep(DomainModel):
    index: int
    type: StepType
    title: str
    status: StepStatus = StepStatus.COMPLETED
    detail: str | None = None
    tool: str | None = None
    params: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    approval_id: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    duration_ms: int | None = None


class Execution(DomainModel):
    id: str
    organization_id: str
    buttlr_id: str
    buttlr_name: str = ""
    conversation_id: str | None = None
    trigger: ExecutionTrigger = ExecutionTrigger.MANUAL
    trigger_detail: str | None = None
    status: ExecutionStatus = ExecutionStatus.QUEUED
    goal: str = ""
    steps: list[ExecutionStep] = Field(default_factory=list)
    output: str | None = None
    error: str | None = None
    model: str | None = None
    provider: str | None = None
    usage: Usage = Field(default_factory=Usage)
    requested_by: str | None = None
    dry_run: bool = False
    pending_approval_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None


class ExecutionSummary(DomainModel):
    """Slim projection for list views — avoids shipping every step."""

    id: str
    organization_id: str
    buttlr_id: str
    buttlr_name: str = ""
    trigger: ExecutionTrigger
    status: ExecutionStatus
    goal: str = ""
    output: str | None = None
    error: str | None = None
    #: Which model provider and model actually served this run.
    provider: str | None = None
    model: str | None = None
    step_count: int = 0
    usage: Usage = Field(default_factory=Usage)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None


def to_summary(execution: Execution) -> ExecutionSummary:
    return ExecutionSummary(
        id=execution.id,
        organization_id=execution.organization_id,
        buttlr_id=execution.buttlr_id,
        buttlr_name=execution.buttlr_name,
        trigger=execution.trigger,
        status=execution.status,
        goal=execution.goal,
        output=execution.output,
        error=execution.error,
        provider=execution.provider,
        model=execution.model,
        step_count=len(execution.steps),
        usage=execution.usage,
        created_at=execution.created_at,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        duration_ms=execution.duration_ms,
    )


class ExecutionEvent(DomainModel):
    """Server-Sent Event payload emitted while a Buttlr works."""

    execution_id: str
    event: str
    step: ExecutionStep | None = None
    status: ExecutionStatus | None = None
    output: str | None = None
    error: str | None = None
    at: datetime = Field(default_factory=utcnow)
