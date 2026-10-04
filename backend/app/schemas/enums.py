"""Enumerations shared across the domain.

All enums are ``str``-valued so they serialise straight to JSON and Firestore.
"""

from __future__ import annotations

from enum import Enum


class OrgRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Permission(str, Enum):
    """Capability levels on a Buttlr. Ordered from weakest to strongest."""

    VIEW = "view"
    ASK = "ask"
    APPROVE = "approve"
    EXECUTE = "execute"
    CONFIGURE = "configure"
    ADMIN = "admin"


PERMISSION_ORDER: dict[Permission, int] = {
    Permission.VIEW: 0,
    Permission.ASK: 1,
    Permission.APPROVE: 2,
    Permission.EXECUTE: 3,
    Permission.CONFIGURE: 4,
    Permission.ADMIN: 5,
}


class GrantSubject(str, Enum):
    EVERYONE = "everyone"
    ROLE = "role"
    TEAM = "team"
    USER = "user"


class ButtlrStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class ModelProviderKind(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"
    HEURISTIC = "heuristic"


class ScheduleKind(str, Enum):
    MANUAL = "manual"
    ONCE = "once"
    INTERVAL = "interval"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CRON = "cron"


class ApprovalMode(str, Enum):
    AUTO = "auto"
    ASK = "ask"
    DENY = "deny"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


class Decision(str, Enum):
    """Outcome of a permission evaluation."""

    ALLOW = "allow"
    DENY = "deny"
    REQUEST_APPROVAL = "request_approval"


class ExecutionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionTrigger(str, Enum):
    SCHEDULE = "schedule"
    MANUAL = "manual"
    CHAT = "chat"
    TEST = "test"
    WEBHOOK = "webhook"
    EVENT = "event"
    APPROVAL_RESUME = "approval_resume"


class StepType(str, Enum):
    STATUS = "status"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_RESULT = "approval_result"
    MESSAGE = "message"
    ERROR = "error"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class IntegrationProvider(str, Enum):
    GITHUB = "github"
    GOOGLE = "google"
    JIRA = "jira"


class IntegrationStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    EXPIRED = "expired"


class AuditAction(str, Enum):
    ORGANIZATION_CREATED = "organization.created"
    ORGANIZATION_UPDATED = "organization.updated"
    MEMBER_INVITED = "member.invited"
    MEMBER_ROLE_CHANGED = "member.role_changed"
    MEMBER_REMOVED = "member.removed"
    TEAM_CREATED = "team.created"
    TEAM_UPDATED = "team.updated"
    TEAM_DELETED = "team.deleted"
    BUTTLR_CREATED = "buttlr.created"
    BUTTLR_UPDATED = "buttlr.updated"
    BUTTLR_DEPLOYED = "buttlr.deployed"
    BUTTLR_PAUSED = "buttlr.paused"
    BUTTLR_DELETED = "buttlr.deleted"
    BUTTLR_TESTED = "buttlr.tested"
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    EXECUTION_CANCELLED = "execution.cancelled"
    TOOL_EXECUTED = "tool.executed"
    TOOL_DENIED = "tool.denied"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_REJECTED = "approval.rejected"
    INTEGRATION_CONNECTED = "integration.connected"
    INTEGRATION_DISCONNECTED = "integration.disconnected"
    SETTINGS_UPDATED = "settings.updated"


class NotificationKind(str, Enum):
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_DECIDED = "approval_decided"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    INTEGRATION_ERROR = "integration_error"
    MEMBER_ADDED = "member_added"
    SYSTEM = "system"


class ActorType(str, Enum):
    USER = "user"
    BUTTLR = "buttlr"
    SYSTEM = "system"


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
