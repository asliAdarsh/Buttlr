"""In-app notifications.

A notification with ``user_id`` unset is organisation-wide: every member of the organisation
sees it. Its read state is tracked per recipient in a ``read_by`` list, while targeted
notifications carry their own ``read`` flag.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.database.base import Condition, Op, Sort, Store, new_id
from app.database.repository import Paths, Repository
from app.schemas.activity import Notification
from app.schemas.enums import NotificationKind

logger = get_logger(__name__)


class NotificationService:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.repo = Repository(store)

    async def notify(
        self,
        organization_id: str,
        kind: NotificationKind,
        title: str,
        body: str = "",
        link: str | None = None,
        user_id: str | None = None,
    ) -> Notification:
        notification = Notification(
            id=new_id(),
            organization_id=organization_id,
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            link=link,
        )
        await self.repo.save(
            Paths.notifications(organization_id), notification.model_dump(mode="python")
        )
        logger.info(
            "notification created org=%s kind=%s user=%s", organization_id, kind, user_id or "*"
        )
        return notification

    async def list(
        self,
        user_id: str,
        organization_id: str,
        *,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        rows = await self.repo.list(
            Paths.notifications(organization_id),
            conditions=[Condition("user_id", Op.EQ, None), Condition("user_id", Op.EQ, user_id)],
            order_by="created_at",
            sort=Sort.DESC,
        )
        results: list[Notification] = []
        for row in rows:
            if unread_only and self._is_read(row, user_id):
                continue
            results.append(self._to_model(row, user_id))
            if len(results) >= limit:
                break
        return results

    async def mark_read(
        self, user_id: str, organization_id: str, notification_id: str
    ) -> Notification:
        collection = Paths.notifications(organization_id)
        row = await self.repo.get(collection, notification_id)
        if row is None:
            raise NotFoundError("Notification not found.")
        owner = row.get("user_id")
        if owner is not None and owner != user_id:
            raise NotFoundError("Notification not found.")
        if owner is not None:
            updated = await self.repo.patch(collection, notification_id, {"read": True})
        else:
            readers = list(row.get("read_by") or [])
            if user_id not in readers:
                readers.append(user_id)
            updated = await self.repo.patch(collection, notification_id, {"read_by": readers})
        return self._to_model(updated, user_id)

    async def mark_all_read(self, user_id: str, organization_id: str) -> int:
        collection = Paths.notifications(organization_id)
        rows = await self.repo.list(
            collection,
            conditions=[Condition("user_id", Op.EQ, None), Condition("user_id", Op.EQ, user_id)],
            order_by=None,
        )
        marked = 0
        for row in rows:
            if self._is_read(row, user_id):
                continue
            if row.get("user_id") == user_id:
                await self.repo.patch(collection, row["id"], {"read": True})
            else:
                readers = list(row.get("read_by") or [])
                readers.append(user_id)
                await self.repo.patch(collection, row["id"], {"read_by": readers})
            marked += 1
        return marked

    async def unread_count(self, user_id: str, organization_id: str) -> int:
        rows = await self.repo.list(
            Paths.notifications(organization_id),
            conditions=[Condition("user_id", Op.EQ, None), Condition("user_id", Op.EQ, user_id)],
            order_by=None,
        )
        return sum(1 for row in rows if not self._is_read(row, user_id))

    @staticmethod
    def _is_read(row: dict[str, Any], user_id: str) -> bool:
        if row.get("user_id") is not None:
            return bool(row.get("read"))
        return user_id in list(row.get("read_by") or [])

    @staticmethod
    def _to_model(row: dict[str, Any], user_id: str) -> Notification:
        model = Notification.model_validate(row)
        if model.user_id is None:
            model.read = user_id in list(row.get("read_by") or [])
        return model