"""Audit trail.

Every state change an operator would want to explain later lands here: who did it, to what,
and when. Writing an audit entry must never be able to break the operation that caused it,
so only store failures propagate.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.database.base import Condition, Op, Store, new_id
from app.database.repository import Paths, Repository
from app.schemas.activity import AuditLog
from app.schemas.common import Page
from app.schemas.enums import ActorType, AuditAction

logger = get_logger(__name__)


class AuditService:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.repo = Repository(store)

    async def record(
        self,
        organization_id: str,
        action: AuditAction,
        *,
        actor_type: ActorType = ActorType.USER,
        actor_id: str | None = None,
        actor_name: str | None = None,
        summary: str = "",
        target_type: str | None = None,
        target_id: str | None = None,
        buttlr_id: str | None = None,
        execution_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            id=new_id(),
            organization_id=organization_id,
            action=action,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_name=actor_name,
            summary=summary,
            target_type=target_type,
            target_id=target_id,
            buttlr_id=buttlr_id,
            execution_id=execution_id,
            metadata=metadata or {},
        )
        await self.repo.save(Paths.audit_logs(organization_id), entry.model_dump(mode="python"))
        return entry

    async def list(
        self,
        organization_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        action: AuditAction | None = None,
        buttlr_id: str | None = None,
    ) -> Page[AuditLog]:
        conditions: list[Condition] = []
        if action is not None:
            conditions.append(Condition("action", Op.EQ, AuditAction(action).value))
        if buttlr_id is not None:
            conditions.append(Condition("buttlr_id", Op.EQ, buttlr_id))
        collection = Paths.audit_logs(organization_id)
        total = await self.repo.count(collection, conditions)
        rows = await self.repo.list(
            collection, conditions=conditions, order_by="created_at", limit=limit, offset=offset
        )
        return Page[AuditLog](
            items=[AuditLog.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )