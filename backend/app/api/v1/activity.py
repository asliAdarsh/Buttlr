"""Audit log and notification routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep, OrgDep
from app.core.errors import PermissionDeniedError
from app.schemas.activity import AuditLog, Notification
from app.schemas.common import Ack, Page
from app.schemas.enums import AuditAction, OrgRole

router = APIRouter(tags=["activity"])


@router.get("/organizations/{organization_id}/audit", response_model=Page[AuditLog])
async def list_audit(
    container: ContainerDep,
    ctx: OrgDep,
    action: AuditAction | None = Query(default=None),
    buttlr_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[AuditLog]:
    if ctx.member.role not in (OrgRole.OWNER, OrgRole.ADMIN):
        raise PermissionDeniedError(
            "Only organization owners and admins can read the full audit log."
        )
    return await container.audit.list(
        ctx.organization.id, limit=limit, offset=offset, action=action, buttlr_id=buttlr_id
    )


@router.get(
    "/organizations/{organization_id}/notifications", response_model=list[Notification]
)
async def list_notifications(
    container: ContainerDep,
    ctx: OrgDep,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Notification]:
    return await container.notifications.list(
        ctx.principal.user_id, ctx.organization.id, unread_only=unread_only, limit=limit
    )


@router.post(
    "/organizations/{organization_id}/notifications/read-all", response_model=Ack
)
async def mark_all_notifications_read(container: ContainerDep, ctx: OrgDep) -> Ack:
    count = await container.notifications.mark_all_read(
        ctx.principal.user_id, ctx.organization.id
    )
    return Ack(ok=True, message=f"{count} notification(s) marked as read.")


@router.post(
    "/organizations/{organization_id}/notifications/{notification_id}/read",
    response_model=Notification,
)
async def mark_notification_read(
    container: ContainerDep, ctx: OrgDep, notification_id: str
) -> Notification:
    return await container.notifications.mark_read(
        ctx.principal.user_id, ctx.organization.id, notification_id
    )
