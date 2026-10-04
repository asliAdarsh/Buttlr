"""Human-in-the-loop approvals."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import DomainModel, utcnow
from app.schemas.enums import ApprovalStatus, RiskLevel


class Approval(DomainModel):
    id: str
    organization_id: str
    buttlr_id: str
    buttlr_name: str = ""
    execution_id: str
    step_index: int = 0
    tool: str
    action: str
    resource: str | None = None
    reason: str = ""
    risk: RiskLevel = RiskLevel.MEDIUM
    params: dict[str, Any] = Field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = None
    decided_by: str | None = None
    decided_by_name: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None


class ApprovalDecision(DomainModel):
    note: str | None = Field(default=None, max_length=500)


class ApprovalStats(DomainModel):
    pending: int = 0
    approved: int = 0
    rejected: int = 0
    expired: int = 0
