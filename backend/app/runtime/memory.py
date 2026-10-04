"""Buttlr memory.

Long-term memory is scoped to one Buttlr inside one organization — an Engineering Buttlr can
never surface Finance context. Memory is only used when ``Buttlr.memory_enabled`` is true.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.database.base import Store, eq, new_id
from app.database.repository import Paths, Repository
from app.schemas.common import utcnow

logger = get_logger(__name__)


class MemoryStoreService:
    def __init__(self, store: Store) -> None:
        self.repo = Repository(store)

    async def remember(
        self,
        organization_id: str,
        buttlr_id: str,
        key: str,
        value: str,
        *,
        kind: str = "fact",
        user_id: str | None = None,
    ) -> dict[str, Any]:
        collection = Paths.memories(organization_id, buttlr_id)
        existing = await self.repo.store.query_one(
            collection, [eq("buttlr_id", buttlr_id), eq("key", key)]
        )
        now = utcnow()
        if existing is not None:
            return await self.repo.patch(
                collection, existing["id"], {"value": value, "kind": kind, "updated_at": now}
            )
        record = {
            "id": new_id(),
            "organization_id": organization_id,
            "buttlr_id": buttlr_id,
            "key": key,
            "value": value,
            "kind": kind,
            "created_by": user_id,
            "created_at": now,
            "updated_at": now,
        }
        return await self.repo.save(collection, record)

    async def recall(
        self,
        organization_id: str,
        buttlr_id: str,
        *,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        collection = Paths.memories(organization_id, buttlr_id)
        rows = await self.repo.list(
            collection,
            conditions=[eq("buttlr_id", buttlr_id)],
            order_by="updated_at",
            limit=200,
        )
        if query:
            needle = query.lower()
            rows = [
                row
                for row in rows
                if needle in str(row.get("key", "")).lower()
                or needle in str(row.get("value", "")).lower()
            ]
        return rows[:limit]

    async def forget(self, organization_id: str, buttlr_id: str, memory_id: str) -> None:
        collection = Paths.memories(organization_id, buttlr_id)
        row = await self.repo.get(collection, memory_id)
        if row is None or row.get("buttlr_id") != buttlr_id:
            raise NotFoundError("Memory not found.")
        await self.repo.delete(collection, memory_id)

    async def clear(self, organization_id: str, buttlr_id: str) -> int:
        collection = Paths.memories(organization_id, buttlr_id)
        return await self.repo.store.delete_many(collection, [eq("buttlr_id", buttlr_id)])

    async def as_prompt_block(self, organization_id: str, buttlr_id: str, *, limit: int = 10) -> str:
        rows = await self.recall(organization_id, buttlr_id, limit=limit)
        if not rows:
            return ""
        lines = [f"- {row.get('key')}: {row.get('value')}" for row in rows]
        return "Things you remember from earlier runs:\n" + "\n".join(lines)


def memory_timestamp() -> datetime:
    return utcnow()


__all__ = ["MemoryStoreService", "memory_timestamp"]
