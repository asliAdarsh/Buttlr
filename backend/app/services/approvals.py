"""Human-in-the-loop approvals.

When a permission evaluation asks for approval the executor parks the run and creates an
:class:`Approval`. A human with sufficient permission on the Buttlr decides; the executor
resumes the run from the stored steps. Expiry is enforced lazily by
:meth:`ApprovalService.expire_stale` — no background timer can lose an approval.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.database.base import Condition, Op, Sort, Store, new_id
from app.database.repository import Paths, Repository
from app.runtime.permissions.engine import AccessContext, PermissionDecision, granted_permission
from app.schemas.approval import Approval, ApprovalStats
from app.schemas.auth import Principal
from app.schemas.buttlr import Buttlr
from app.schemas.common import Page, utcnow
from app.schemas.enums import (
    PERMISSION_ORDER,
    ActorType,
    ApprovalStatus,
    AuditAction,
    NotificationKind,
)
from app.schemas.execution import Execution
from app.schemas.organization import Member, Organization, OrganizationSettings
from app.services.audit import AuditService
from app.services.notifications import NotificationService

logger = get_logger(__name__)

_STATUS_KEYS: dict[ApprovalStatus, str] = {
    ApprovalStatus.PENDING: "pending",
    ApprovalStatus.APPROVED: "approved",
    ApprovalStatus.REJECTED: "rejected",
    ApprovalStatus.EXPIRED: "expired",
}


class ApprovalService:
    def __init__(
        self, store: Store, audit: AuditService, notifications: NotificationService
    ) -> None:
        self.store = store
        self.audit = audit
        self.notifications = notifications
        self.repo = Repository(store)

    # ---- reads ------------------------------------------------------------

    async def get(self, organization_id: str, approval_id: str) -> Approval:
        raw = await self.repo.get(Paths.approvals(organization_id), approval_id)
        if raw is None:
            raise NotFoundError("That approval request no longer exists.")
        return Approval.model_validate(raw)

    async def list(
        self,
        organization_id: str,
        *,
        status: ApprovalStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[Approval]:
        conditions: list[Condition] = []
        if status is not None:
            conditions.append(Condition("status", Op.EQ, ApprovalStatus(status).value))
        collection = Paths.approvals(organization_id)
        total = await self.repo.count(collection, conditions)
        rows = await self.repo.list(
            collection,
            conditions=conditions,
            order_by="requested_at",
            sort=Sort.DESC,
            limit=limit,
            offset=offset,
        )
        return Page[Approval](
            items=[Approval.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def pending_for_org(self, organization_id: str) -> int:
        return await self.repo.count(
            Paths.approvals(organization_id),
            [Condition("status", Op.EQ, ApprovalStatus.PENDING.value)],
        )

    async def stats(self, organization_id: str) -> ApprovalStats:
        """Counts per status — the approvals dashboard reads only this."""
        rows = await self.repo.list(
            Paths.approvals(organization_id), order_by=None, sort=Sort.DESC
        )
        counts = dict.fromkeys(_STATUS_KEYS.values(), 0)
        for row in rows:
            try:
                status = ApprovalStatus(row.get("status"))
            except ValueError:
                continue
            key = _STATUS_KEYS.get(status)
            if key is not None:
                counts[key] += 1
        return ApprovalStats.model_validate(counts)

    # ---- writes -----------------------------------------------------------

    async def create(
        self,
        *,
        organization: Organization,
        buttlr: Buttlr,
        execution: Execution,
        step_index: int,
        decision: PermissionDecision,
        action: str,
        resource: str | None = None,
        reason: str = "",
        params: dict[str, Any] | None = None,
    ) -> Approval:
        expiry_minutes = buttlr.approval_policy.expiry_minutes
        expires_at = (
            utcnow() + timedelta(minutes=expiry_minutes) if expiry_minutes else None
        )
        approval = Approval(
            id=new_id(),
            organization_id=organization.id,
            buttlr_id=buttlr.id,
            buttlr_name=buttlr.name,
            execution_id=execution.id,
            step_index=step_index,
            tool=decision.tool,
            action=action,
            resource=resource,
            reason=reason or decision.reason,
            risk=decision.risk,
            params=params or {},
            status=ApprovalStatus.PENDING,
            expires_at=expires_at,
        )
        await self.repo.save(
            Paths.approvals(organization.id), approval.model_dump(mode="python")
        )
        await self.audit.record(
            organization.id,
            AuditAction.APPROVAL_REQUESTED,
            actor_type=ActorType.BUTTLR,
            actor_id=buttlr.id,
            actor_name=buttlr.name,
            summary=f"{buttlr.name} needs approval to {action}.",
            target_type="approval",
            target_id=approval.id,
            buttlr_id=buttlr.id,
            execution_id=execution.id,
            metadata={
                "tool": approval.tool,
                "risk": approval.risk.value,
                "reason": approval.reason,
            },
        )
        body = approval.reason or approval.action
        await self.notifications.notify(
            organization.id,
            NotificationKind.APPROVAL_REQUIRED,
            f"{buttlr.name} needs your approval",
            body,
            link=f"/approvals/{approval.id}",
        )
        return approval

    async def decide(
        self,
        principal: Principal,
        organization_id: str,
        approval_id: str,
        granted: bool,
        note: str | None = None,
    ) -> Approval:
        approval = await self.get(organization_id, approval_id)
        if approval.status != ApprovalStatus.PENDING:
            raise ConflictError(f"This request was already {approval.status.value}.")

        buttlr_raw = await self.repo.get(Paths.buttlrs(organization_id), approval.buttlr_id)
        if buttlr_raw is None:
            raise NotFoundError("The Buttlr that asked for approval no longer exists.")
        buttlr = Buttlr.model_validate(buttlr_raw)
        await self._authorize_decision(principal, organization_id, buttlr, approval, granted)

        now = utcnow()
        approval.status = ApprovalStatus.APPROVED if granted else ApprovalStatus.REJECTED
        approval.decided_by = principal.user_id
        approval.decided_by_name = principal.display_name
        approval.decided_at = now
        approval.decision_note = note
        await self.repo.save(
            Paths.approvals(organization_id), approval.model_dump(mode="python")
        )

        verb = "approved" if granted else "rejected"
        await self.audit.record(
            organization_id,
            AuditAction.APPROVAL_GRANTED if granted else AuditAction.APPROVAL_REJECTED,
            actor_type=ActorType.USER,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"{principal.display_name} {verb} {approval.action} for {buttlr.name}.",
            target_type="approval",
            target_id=approval.id,
            buttlr_id=buttlr.id,
            execution_id=approval.execution_id,
            metadata={"note": note or ""},
        )
        await self.notifications.notify(
            organization_id,
            NotificationKind.APPROVAL_DECIDED,
            f"{approval.action} was {verb}",
            note or f"{principal.display_name} {verb} this action.",
            link=f"/approvals/{approval.id}",
            user_id=buttlr.created_by,
        )
        return approval

    async def expire_stale(self, organization_id: str) -> int:
        """Retire pending requests whose window has closed. Returns how many expired."""
        collection = Paths.approvals(organization_id)
        rows = await self.repo.list(
            collection,
            conditions=[Condition("status", Op.EQ, ApprovalStatus.PENDING.value)],
            order_by="requested_at",
            sort=Sort.DESC,
        )
        now = utcnow()
        expired = 0
        for row in rows:
            raw_expiry = row.get("expires_at")
            if not isinstance(raw_expiry, datetime):
                continue
            expires_at = raw_expiry
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=now.tzinfo)
            if expires_at > now:
                continue
            await self.repo.patch(
                collection, row["id"], {"status": ApprovalStatus.EXPIRED.value}
            )
            expired += 1
        if expired:
            logger.info("Expired %s stale approval(s) in %s", expired, organization_id)
        return expired

    # ---- internals --------------------------------------------------------

    async def _authorize_decision(
        self,
        principal: Principal,
        organization_id: str,
        buttlr: Buttlr,
        approval: Approval,
        granted: bool,
    ) -> None:
        """Only an actor holding the policy's approver permission may decide.

        The caller who triggered the run may always reject their own request — refusing to
        let your own Buttlr act is never a privilege escalation.
        """
        member_raw = await self.repo.get(Paths.members(organization_id), principal.user_id)
        if member_raw is None:
            raise PermissionDeniedError("You are not a member of this organization.")
        member = Member.model_validate(member_raw)

        organization_raw = await self.repo.get(Paths.ORGANIZATIONS, organization_id)
        settings = (
            Organization.model_validate(organization_raw).settings
            if organization_raw is not None
            else OrganizationSettings()
        )
        access = AccessContext(
            user_id=principal.user_id,
            org_role=member.role,
            team_ids=tuple(member.team_ids),
            settings=settings,
        )

        required = buttlr.approval_policy.approver_permission
        level = granted_permission(buttlr, access)
        allowed = level is not None and PERMISSION_ORDER[level] >= PERMISSION_ORDER[required]
        if not allowed and not granted:
            requester = await self._requested_by(organization_id, approval)
            allowed = requester is not None and requester == principal.user_id
        if not allowed:
            raise PermissionDeniedError(
                f"Only someone with {required.value} permission on {buttlr.name} "
                "can decide this request."
            )

    async def _requested_by(self, organization_id: str, approval: Approval) -> str | None:
        """The user whose run produced this request, read from the execution."""
        raw = await self.repo.get(Paths.executions(organization_id), approval.execution_id)
        return Execution.model_validate(raw).requested_by if raw is not None else None
