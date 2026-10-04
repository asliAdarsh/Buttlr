"""Analytics and the dashboard.

Every number on the analytics screen is computed from real stored documents: the executions
that ran, the tool calls they actually made, and the approvals humans actually decided.
Nothing here is seeded, estimated from a config value, or hard-coded — if a Buttlr never
ran, its row stays at zero.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from app.core.errors import PermissionDeniedError
from app.core.logging import get_logger
from app.database.base import Condition, Op, Sort, Store
from app.database.repository import Paths, Repository
from app.runtime.permissions.engine import AccessContext, engine
from app.schemas.activity import (
    AnalyticsOverview,
    AuditLog,
    DashboardOverview,
    ModelUsageBreakdown,
    TimeBucket,
    ToolUsageBreakdown,
)
from app.schemas.approval import Approval
from app.schemas.auth import Principal
from app.schemas.buttlr import Buttlr
from app.schemas.common import utcnow
from app.schemas.enums import (
    ApprovalStatus,
    ButtlrStatus,
    ExecutionStatus,
    IntegrationProvider,
    Permission,
    StepType,
)
from app.schemas.execution import Execution, to_summary
from app.schemas.organization import Member, Organization, OrganizationSettings

logger = get_logger(__name__)

#: Terminal statuses that count towards the success rate. A cancelled run is neither a
#: success nor a failure, so it is excluded from the ratio but still counted as a run.
SUCCESS_STATUSES: frozenset[ExecutionStatus] = frozenset({ExecutionStatus.COMPLETED})
FAILURE_STATUSES: frozenset[ExecutionStatus] = frozenset(
    {ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}
)

#: Statuses that mean a run is in flight right now.
ACTIVE_EXECUTION_STATUSES: frozenset[ExecutionStatus] = frozenset(
    {ExecutionStatus.QUEUED, ExecutionStatus.RUNNING, ExecutionStatus.WAITING_APPROVAL}
)

#: One run is credited with at most this many minutes of saved time; a run that reported a
#: long wall-clock duration (a waiting-for-approval run, for example) must not inflate the
#: headline figure without bound.
MAX_CREDITED_MINUTES_PER_RUN = 60.0

_DASHBOARD_RECENT_LIMIT = 5

#: The dashboard reads at most this many executions when computing today's totals.
_DASHBOARD_EXECUTION_SCAN = 200


class AnalyticsService:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.repo = Repository(store)

    # ---- overview ---------------------------------------------------------

    async def overview(self, organization_id: str, days: int = 30) -> AnalyticsOverview:
        """Aggregate every real execution in the trailing window."""
        window = max(1, int(days))
        now = utcnow()
        cutoff = now - timedelta(days=window)

        rows = await self.repo.list(
            Paths.executions(organization_id),
            conditions=[
                Condition("created_at", Op.GTE, cutoff),
            ],
            order_by="created_at",
            sort=Sort.ASC,
        )
        executions = [Execution.model_validate(row) for row in rows]

        completed = sum(1 for e in executions if e.status == ExecutionStatus.COMPLETED)
        failed = sum(1 for e in executions if e.status in FAILURE_STATUSES)

        durations = [e.duration_ms for e in executions if e.duration_ms]
        avg_duration_ms = round(sum(durations) / len(durations)) if durations else 0

        total_tokens = sum(e.usage.total_tokens for e in executions)
        total_cost = round(sum(e.usage.estimated_cost_usd for e in executions), 6)

        approvals = await self._approvals(organization_id)
        approved = sum(1 for a in approvals if a.status == ApprovalStatus.APPROVED)
        rejected = sum(1 for a in approvals if a.status == ApprovalStatus.REJECTED)
        pending = sum(1 for a in approvals if a.status == ApprovalStatus.PENDING)

        latencies = [
            (a.decided_at - a.requested_at).total_seconds() / 60.0
            for a in approvals
            if a.decided_at is not None
        ]
        avg_approval_minutes = round(sum(latencies) / len(latencies), 1) if latencies else 0.0

        return AnalyticsOverview(
            executions_total=len(executions),
            executions_completed=completed,
            executions_failed=failed,
            success_rate=_rate(completed, completed + failed),
            avg_duration_ms=avg_duration_ms,
            total_tokens=total_tokens,
            estimated_cost_usd=total_cost,
            approvals_pending=pending,
            approvals_approved=approved,
            approvals_rejected=rejected,
            avg_approval_minutes=avg_approval_minutes,
            estimated_minutes_saved=self._minutes_saved(executions),
            timeline=self._timeline(executions, now, window),
            by_model=_by_model(executions),
            by_tool=_by_tool(executions),
        )

    # ---- dashboard --------------------------------------------------------

    async def dashboard(
        self, principal: Principal, organization_id: str
    ) -> DashboardOverview:
        """The landing view: what this organization is, and what happened today.

        Organization-wide counts describe the whole tenant, but the Buttlr cards and the
        recent activity are filtered to what this caller may actually view: grants are
        per-Buttlr, so a member must not see a Buttlr they were never granted.
        """
        membership_raw = await self.repo.membership(organization_id, principal.user_id)
        if membership_raw is None:
            raise PermissionDeniedError("You are not a member of this organization.")
        membership = Member.model_validate(membership_raw)

        org_raw = await self.repo.get(Paths.ORGANIZATIONS, organization_id)
        organization: Any = Organization.model_validate(org_raw) if org_raw else None
        access = AccessContext(
            user_id=principal.user_id,
            org_role=membership.role,
            team_ids=tuple(membership.team_ids),
            settings=organization.settings if organization else OrganizationSettings(),
        )

        buttlrs_path = Paths.buttlrs(organization_id)
        buttlrs_total = await self.repo.count(buttlrs_path)
        buttlrs_active = await self.repo.count(
            buttlrs_path, [Condition("status", Op.EQ, ButtlrStatus.ACTIVE.value)]
        )
        teams_total = await self.repo.count(Paths.teams(organization_id))
        members_total = await self.repo.count(Paths.members(organization_id))

        integrations_connected = await self.repo.count(
            Paths.integrations(organization_id),
            [Condition("status", Op.EQ, "connected")],
        )

        today = _local_date(utcnow())
        recent_raw = await self.repo.list(
            Paths.executions(organization_id), order_by="created_at", sort=Sort.DESC
        )
        recent = [
            Execution.model_validate(row)
            for row in recent_raw[:_DASHBOARD_EXECUTION_SCAN]
        ]

        todays = [e for e in recent if _local_date(e.created_at) == today]
        running_buttlrs = {
            e.buttlr_id for e in recent if e.status in ACTIVE_EXECUTION_STATUSES
        }

        approvals_pending = await self.repo.count(
            Paths.approvals(organization_id), [Condition("status", Op.EQ, "pending")]
        )

        audit_rows = await self.repo.list(
            Paths.audit_logs(organization_id),
            order_by="created_at",
            sort=Sort.DESC,
            limit=_DASHBOARD_RECENT_LIMIT,
        )
        # Load the Buttlr documents before slicing: grants are per-Buttlr, so filtering
        # after the limit would leave the viewer with a short list of visible Buttlrs.
        buttlr_rows = await self.repo.list(
            buttlrs_path, order_by="created_at", sort=Sort.DESC
        )
        visible = [
            buttlr
            for buttlr in (Buttlr.model_validate(row) for row in buttlr_rows)
            if engine.can(buttlr=buttlr, access=access, permission=Permission.VIEW)
        ]
        visible_ids = {buttlr.id for buttlr in visible}

        return DashboardOverview(
            organization=organization,
            buttlrs_total=buttlrs_total,
            buttlrs_active=buttlrs_active,
            buttlrs_running=len(running_buttlrs),
            teams_total=teams_total,
            members_total=members_total,
            integrations_connected=integrations_connected,
            integrations_total=len(list(IntegrationProvider)),
            approvals_pending=approvals_pending,
            executions_today=len(todays),
            executions_failed_today=sum(
                1 for e in todays if e.status in FAILURE_STATUSES
            ),
            estimated_minutes_saved=self._minutes_saved(recent),
            recent_executions=[
                to_summary(e)
                for e in recent
                if e.buttlr_id in visible_ids
            ][:_DASHBOARD_RECENT_LIMIT],
            recent_audit=[AuditLog.model_validate(row) for row in audit_rows],
            buttlrs=visible[:_DASHBOARD_RECENT_LIMIT],
        )

    # ---- internals --------------------------------------------------------

    async def _approvals(self, organization_id: str) -> list[Approval]:
        rows = await self.repo.list(Paths.approvals(organization_id), order_by=None)
        return [Approval.model_validate(row) for row in rows]

    @staticmethod
    def _minutes_saved(executions: list[Execution]) -> int:
        """Credit every settled, successful run with the time it took — at least one
        minute, and never more than an hour for a single run."""
        total = 0.0
        for execution in executions:
            if execution.status not in SUCCESS_STATUSES:
                continue
            minutes = (execution.duration_ms or 0) / 60_000.0
            total += max(1.0, min(minutes, MAX_CREDITED_MINUTES_PER_RUN))
        return round(total)

    @staticmethod
    def _timeline(
        executions: list[Execution], now: datetime, window: int
    ) -> list[TimeBucket]:
        """One bucket per day in the window, oldest first, with gaps filled as zero."""
        by_day: dict[date, list[Execution]] = defaultdict(list)
        for execution in executions:
            by_day[_local_date(execution.created_at)].append(execution)

        buckets: list[TimeBucket] = []
        last_day = _local_date(now)
        for offset in range(window - 1, -1, -1):
            day = last_day - timedelta(days=offset)
            bucket_executions = by_day.get(day, [])
            buckets.append(
                TimeBucket(
                    label=day.strftime("%a"),
                    date=day.isoformat(),
                    total=len(bucket_executions),
                    completed=sum(
                        1 for e in bucket_executions if e.status in SUCCESS_STATUSES
                    ),
                    failed=sum(1 for e in bucket_executions if e.status in FAILURE_STATUSES),
                )
            )
        return buckets


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


def _local_date(value: datetime) -> date:
    stamp = value.astimezone() if value.tzinfo is not None else value
    return stamp.date()


def _model_label(execution: Execution) -> tuple[str, str]:
    """Executions record ``model`` as ``"<provider>:<name>"`` and may carry a separate
    ``provider`` once a run actually reached a provider."""
    if execution.provider:
        model = execution.model or "auto"
        if model.startswith(f"{execution.provider}:"):
            model = model.split(":", 1)[1]
        return execution.provider, model
    if execution.model and ":" in execution.model:
        provider, _, name = execution.model.partition(":")
        return provider, name
    return "unknown", execution.model or "auto"


def _by_model(executions: list[Execution]) -> list[ModelUsageBreakdown]:
    """Runs, tokens and cost per provider · model that actually served them.

    A run counts even when the provider reports no token usage — the deterministic planner
    does exactly that, and leaving it out would hide every offline run.
    """
    totals: dict[tuple[str, str], ModelUsageBreakdown] = {}
    for execution in executions:
        provider, model = _model_label(execution)
        key = (provider, model)
        entry = totals.get(key)
        if entry is None:
            entry = ModelUsageBreakdown(provider=provider, model=model)
            totals[key] = entry
        entry.calls += max(execution.usage.calls, 1)
        entry.input_tokens += execution.usage.input_tokens
        entry.output_tokens += execution.usage.output_tokens
        entry.estimated_cost_usd = round(
            entry.estimated_cost_usd + execution.usage.estimated_cost_usd, 6
        )
    return sorted(totals.values(), key=lambda m: (m.provider, m.model))


def _by_tool(executions: list[Execution]) -> list[ToolUsageBreakdown]:
    """Every ``TOOL_RESULT`` step is one real tool invocation; ``ok is False`` is a failure."""
    totals: dict[str, ToolUsageBreakdown] = {}
    for execution in executions:
        for step in execution.steps:
            if step.type != StepType.TOOL_RESULT or not step.tool:
                continue
            entry = totals.get(step.tool)
            if entry is None:
                entry = ToolUsageBreakdown(tool=step.tool)
                totals[step.tool] = entry
            entry.calls += 1
            result = step.result if isinstance(step.result, dict) else {}
            if result.get("ok") is False:
                entry.failures += 1
    return sorted(totals.values(), key=lambda t: (-t.calls, t.tool))


__all__ = ["AnalyticsService"]
