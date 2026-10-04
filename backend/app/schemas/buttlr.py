"""The Buttlr itself: configuration, scope, schedule, permissions, approval policy."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from app.schemas.common import DomainModel, utcnow
from app.schemas.enums import (
    ApprovalMode,
    ButtlrStatus,
    ExecutionStatus,
    GrantSubject,
    ModelProviderKind,
    Permission,
    RiskLevel,
    ScheduleKind,
)


class ModelConfig(DomainModel):
    """Which model a Buttlr reasons with. ``provider='auto'`` lets the router decide."""

    provider: str = "auto"
    name: str = "auto"
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=256, le=32000)
    fallback: list[str] = Field(default_factory=list)

    @property
    def label(self) -> str:
        if self.provider == "auto" or self.provider == ModelProviderKind.HEURISTIC.value:
            return "Auto (platform default)"
        return f"{self.provider} · {self.name}"


class Schedule(DomainModel):
    enabled: bool = False
    kind: ScheduleKind = ScheduleKind.MANUAL
    timezone: str = "UTC"
    at: str | None = None
    day_of_week: str | None = None
    day_of_month: int | None = None
    interval_minutes: int | None = None
    run_at: datetime | None = None
    cron: str | None = None
    business_hours_only: bool = False

    @field_validator("at")
    @classmethod
    def _validate_at(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parts = value.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError("time must be HH:MM")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("time must be HH:MM")
        return f"{hour:02d}:{minute:02d}"

    def describe(self) -> str:
        if not self.enabled or self.kind == ScheduleKind.MANUAL:
            return "Manual only"
        if self.kind == ScheduleKind.ONCE:
            return f"Once at {self.run_at:%Y-%m-%d %H:%M}" if self.run_at else "Once"
        if self.kind == ScheduleKind.HOURLY:
            return "Every hour"
        if self.kind == ScheduleKind.INTERVAL:
            return f"Every {self.interval_minutes or 60} minutes"
        if self.kind == ScheduleKind.DAILY:
            return f"Every day at {self.at or '09:00'}"
        if self.kind == ScheduleKind.WEEKLY:
            return f"Every {(self.day_of_week or 'mon').title()} at {self.at or '09:00'}"
        if self.kind == ScheduleKind.MONTHLY:
            return f"Day {self.day_of_month or 1} of each month at {self.at or '09:00'}"
        if self.kind == ScheduleKind.CRON:
            return f"Cron {self.cron}"
        return self.kind.value


class ApprovalRule(DomainModel):
    tool: str
    mode: ApprovalMode
    approver_roles: list[str] = Field(default_factory=list)


class ApprovalPolicy(DomainModel):
    default_mode: ApprovalMode = ApprovalMode.AUTO
    rules: list[ApprovalRule] = Field(default_factory=list)
    require_for_risk: RiskLevel = RiskLevel.HIGH
    approver_permission: Permission = Permission.APPROVE
    expiry_minutes: int | None = 1440


class PermissionGrant(DomainModel):
    subject_type: GrantSubject
    subject: str
    permission: Permission


class KnowledgeSource(DomainModel):
    id: str
    kind: str = "url"
    name: str
    location: str
    created_at: datetime = Field(default_factory=utcnow)


class ButtlrStats(DomainModel):
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    last_run_at: datetime | None = None
    last_status: ExecutionStatus | None = None
    last_duration_ms: int | None = None
    pending_approvals: int = 0
    estimated_minutes_saved: int = 0

    @property
    def success_rate(self) -> float:
        finished = self.successful_runs + self.failed_runs
        if finished == 0:
            return 0.0
        return round(self.successful_runs / finished * 100, 1)


class Buttlr(DomainModel):
    id: str
    organization_id: str
    team_id: str | None = None
    name: str
    avatar: str = "🤖"
    role: str = "AI Assistant"
    department: str | None = None
    description: str = ""
    objective: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    instructions: str = ""
    model: ModelConfig = Field(default_factory=ModelConfig)
    tools: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    knowledge: list[KnowledgeSource] = Field(default_factory=list)
    schedule: Schedule = Field(default_factory=Schedule)
    status: ButtlrStatus = ButtlrStatus.DRAFT
    approval_policy: ApprovalPolicy = Field(default_factory=ApprovalPolicy)
    permissions: list[PermissionGrant] = Field(default_factory=list)
    memory_enabled: bool = True
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    deployed_at: datetime | None = None
    stats: ButtlrStats = Field(default_factory=ButtlrStats)

    @property
    def needs_approval_tools(self) -> list[str]:
        return [rule.tool for rule in self.approval_policy.rules if rule.mode == ApprovalMode.ASK]


class ButtlrCreate(DomainModel):
    name: str = Field(min_length=2, max_length=80)
    avatar: str = "🤖"
    role: str = "AI Assistant"
    team_id: str | None = None
    department: str | None = None
    description: str = ""
    objective: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    instructions: str = ""
    model: ModelConfig | None = None
    tools: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    schedule: Schedule | None = None
    approval_policy: ApprovalPolicy | None = None
    permissions: list[PermissionGrant] = Field(default_factory=list)
    memory_enabled: bool = True
    status: ButtlrStatus = ButtlrStatus.DRAFT


class ButtlrUpdate(DomainModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    avatar: str | None = None
    role: str | None = None
    team_id: str | None = None
    department: str | None = None
    description: str | None = None
    objective: str | None = None
    responsibilities: list[str] | None = None
    instructions: str | None = None
    model: ModelConfig | None = None
    tools: list[str] | None = None
    integrations: list[str] | None = None
    scope: dict[str, Any] | None = None
    schedule: Schedule | None = None
    status: ButtlrStatus | None = None
    approval_policy: ApprovalPolicy | None = None
    permissions: list[PermissionGrant] | None = None
    memory_enabled: bool | None = None


class ButtlrDraftRequest(DomainModel):
    """Natural-language Buttlr creation."""

    prompt: str = Field(min_length=10, max_length=4000)
    organization_id: str
    team_id: str | None = None


class ButtlrRefineRequest(DomainModel):
    instruction: str = Field(min_length=3, max_length=1000)
    current: ButtlrCreate


class ButtlrDraftResponse(DomainModel):
    draft: ButtlrCreate
    rationale: str = ""
    assumptions: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    provider: str = "heuristic"
    model: str = "heuristic"


class ButtlrRunRequest(DomainModel):
    input: str | None = Field(default=None, max_length=4000)
    dry_run: bool = False
