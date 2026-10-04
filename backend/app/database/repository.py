"""Typed helpers over ``Store``.

Collection paths live here so no service has to remember how documents are nested.
"""

from __future__ import annotations

from typing import Any

from app.database.base import Condition, Op, Query, Sort, Store, new_id


def org_path(organization_id: str, *parts: str) -> str:
    segments = ["organizations", organization_id, *parts]
    return "/".join(segments)


class Paths:
    USERS = "users"
    ORGANIZATIONS = "organizations"

    @staticmethod
    def members(organization_id: str) -> str:
        return org_path(organization_id, "members")

    @staticmethod
    def teams(organization_id: str) -> str:
        return org_path(organization_id, "teams")

    @staticmethod
    def buttlrs(organization_id: str) -> str:
        return org_path(organization_id, "buttlrs")

    @staticmethod
    def integrations(organization_id: str) -> str:
        return org_path(organization_id, "integrations")

    @staticmethod
    def oauth_apps(organization_id: str) -> str:
        """A workspace's own OAuth applications, one document per provider."""
        return org_path(organization_id, "oauthApps")

    @staticmethod
    def executions(organization_id: str) -> str:
        return org_path(organization_id, "executions")

    @staticmethod
    def approvals(organization_id: str) -> str:
        return org_path(organization_id, "approvals")

    @staticmethod
    def audit_logs(organization_id: str) -> str:
        return org_path(organization_id, "auditLogs")

    @staticmethod
    def notifications(organization_id: str) -> str:
        return org_path(organization_id, "notifications")

    @staticmethod
    def conversations(organization_id: str, buttlr_id: str) -> str:
        return org_path(organization_id, "buttlrs", buttlr_id, "conversations")

    @staticmethod
    def messages(organization_id: str, buttlr_id: str, conversation_id: str) -> str:
        return org_path(
            organization_id, "buttlrs", buttlr_id, "conversations", conversation_id, "messages"
        )

    @staticmethod
    def memories(organization_id: str, buttlr_id: str) -> str:
        return org_path(organization_id, "buttlrs", buttlr_id, "memory")


class Repository:
    def __init__(self, store: Store) -> None:
        self.store = store

    # ---- generic ----------------------------------------------------------

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        return await self.store.get(collection, doc_id)

    async def save(self, collection: str, data: dict[str, Any]) -> dict[str, Any]:
        doc_id = data.get("id") or new_id()
        payload = {**data, "id": doc_id}
        return await self.store.set(collection, doc_id, payload, merge=False)

    async def patch(
        self, collection: str, doc_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        return await self.store.update(collection, doc_id, changes)

    async def delete(self, collection: str, doc_id: str) -> None:
        await self.store.delete(collection, doc_id)

    async def list(
        self,
        collection: str,
        *,
        conditions: list[Condition] | None = None,
        order_by: str | None = "created_at",
        sort: Sort = Sort.DESC,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return await self.store.query(
            collection,
            Query(
                conditions=conditions or [],
                order_by=order_by,
                sort=sort,
                limit=limit,
                offset=offset,
            ),
        )

    async def count(
        self, collection: str, conditions: list[Condition] | None = None
    ) -> int:
        return await self.store.count(collection, conditions)

    async def query_one(
        self, collection: str, conditions: list[Condition]
    ) -> dict[str, Any] | None:
        """First document matching every condition, or ``None``."""
        return await self.store.query_one(collection, conditions)

    async def group(
        self,
        collection_group: str,
        *,
        conditions: list[Condition] | None = None,
        order_by: str | None = None,
        sort: Sort = Sort.DESC,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return await self.store.query_group(
            collection_group,
            Query(conditions=conditions or [], order_by=order_by, sort=sort, limit=limit),
        )

    # ---- users ------------------------------------------------------------

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        return await self.store.get(Paths.USERS, user_id)

    async def upsert_user(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return await self.store.set(Paths.USERS, user_id, {**data, "id": user_id}, merge=True)

    # ---- memberships ------------------------------------------------------

    async def memberships_for_user(self, user_id: str) -> list[dict[str, Any]]:
        return await self.group(
            "members", conditions=[Condition("user_id", Op.EQ, user_id)], order_by=None
        )

    async def membership(self, organization_id: str, user_id: str) -> dict[str, Any] | None:
        return await self.store.get(Paths.members(organization_id), user_id)

    async def save_membership(
        self, organization_id: str, user_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        return await self.store.set(
            Paths.members(organization_id), user_id, {**data, "id": user_id}, merge=True
        )
