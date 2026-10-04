"""Audit log, notifications, chat and analytics schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import DomainModel, utcnow
from app.schemas.enums import ActorType, AuditAction, ChatRole, NotificationKind


class AuditLog(DomainModel):
    id: str
    organization_id: str
    action: AuditAction
    actor_type: ActorType = ActorType.USER
    actor_id: str | None = None
    actor_name: str | None = None
    summary: str = ""
    target_type: str | None = None
    target_id: str | None = None
    buttlr_id: str | None = None
    execution_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class Notification(DomainModel):
    id: str
    organization_id: str
    user_id: str | None = None
    kind: NotificationKind
    title: str
    body: str = ""
    link: str | None = None
    read: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class ChatMessage(DomainModel):
    id: str
    organization_id: str
    buttlr_id: str
    conversation_id: str
    role: ChatRole
    content: str
    execution_id: str | None = None
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ChatRequest(DomainModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    dry_run: bool = False


class ChatResponse(DomainModel):
    conversation_id: str
    reply: ChatMessage
    execution_id: str | None = None
    pending_approval_id: str | None = None


class Conversation(DomainModel):
    id: str
    organization_id: str
    buttlr_id: str
    title: str = "New conversation"
    created_by: str | None = None
    message_count: int = 0
    updated_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)


class TimeBucket(DomainModel):
    label: str
    date: str
    total: int = 0
    completed: int = 0
    failed: int = 0


class ModelUsageBreakdown(DomainModel):
    provider: str
    model: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0


class ToolUsageBreakdown(DomainModel):
    tool: str
    calls: int = 0
    failures: int = 0


class AnalyticsOverview(DomainModel):
    executions_total: int = 0
    executions_completed: int = 0
    executions_failed: int = 0
    success_rate: float = 0.0
    avg_duration_ms: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    approvals_pending: int = 0
    approvals_approved: int = 0
    approvals_rejected: int = 0
    avg_approval_minutes: float = 0.0
    estimated_minutes_saved: int = 0
    timeline: list[TimeBucket] = Field(default_factory=list)
    by_model: list[ModelUsageBreakdown] = Field(default_factory=list)
    by_tool: list[ToolUsageBreakdown] = Field(default_factory=list)


class DashboardOverview(DomainModel):
    organization: Any
    buttlrs_total: int = 0
    buttlrs_active: int = 0
    buttlrs_running: int = 0
    teams_total: int = 0
    members_total: int = 0
    integrations_connected: int = 0
    integrations_total: int = 0
    approvals_pending: int = 0
    executions_today: int = 0
    executions_failed_today: int = 0
    estimated_minutes_saved: int = 0
    recent_executions: list[Any] = Field(default_factory=list)
    recent_audit: list[Any] = Field(default_factory=list)
    buttlrs: list[Any] = Field(default_factory=list)
