"""Persistence contract.

Buttlr stores documents in collections addressed by path (``organizations/{id}/buttlrs``).
Two implementations satisfy this interface — Firestore for production, an in-memory/file
store for development — so domain code never branches on the backend.
"""

from __future__ import annotations

import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Op(str, Enum):
    EQ = "=="
    NE = "!="
    IN = "in"
    NOT_IN = "not-in"
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    ARRAY_CONTAINS = "array_contains"
    ARRAY_CONTAINS_ANY = "array_contains_any"


class Sort(str, Enum):
    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True)
class Condition:
    field: str
    op: Op
    value: Any


@dataclass
class Query:
    conditions: list[Condition] = field(default_factory=list)
    order_by: str | None = None
    sort: Sort = Sort.DESC
    limit: int | None = None
    offset: int = 0


_id_lock = threading.Lock()
_id_millisecond = 0
_id_sequence = 0


def new_id() -> str:
    """A time-sortable, monotonic identifier.

    The clock hands the same millisecond to documents written in a row (Windows resolves
    about 15 ms), so a timestamp alone cannot order them: messages in one chat, steps in one
    run and audit rows all collide. A counter inside the millisecond makes the id a usable
    tiebreaker in every store.
    """
    global _id_millisecond, _id_sequence
    with _id_lock:
        now_ms = int(time.time() * 1000)
        if now_ms == _id_millisecond:
            _id_sequence += 1
        else:
            _id_millisecond = now_ms
            _id_sequence = 0
        return f"{now_ms:013d}{_id_sequence:04d}{uuid.uuid4().hex[:6]}"


def eq(field_name: str, value: Any) -> Condition:
    return Condition(field_name, Op.EQ, value)


class Store(ABC):
    """Async document store."""

    backend: str = "unknown"

    @abstractmethod
    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def create(
        self, collection: str, data: dict[str, Any], doc_id: str | None = None
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def set(
        self, collection: str, doc_id: str, data: dict[str, Any], merge: bool = True
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def update(
        self, collection: str, doc_id: str, patch: dict[str, Any]
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def delete(self, collection: str, doc_id: str) -> None: ...

    @abstractmethod
    async def query(self, collection: str, query: Query | None = None) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def count(
        self, collection: str, conditions: list[Condition] | None = None
    ) -> int: ...

    @abstractmethod
    async def query_group(
        self, collection_group: str, query: Query | None = None
    ) -> list[dict[str, Any]]:
        """Query every collection with this name, regardless of parent.

        Used for "which organizations does this user belong to?" without scanning the tree.
        Documents carry their own ``organization_id``, so a plain condition is enough.
        """

    async def query_one(
        self, collection: str, conditions: list[Condition]
    ) -> dict[str, Any] | None:
        rows = await self.query(collection, Query(conditions=conditions, limit=1))
        return rows[0] if rows else None

    async def delete_many(self, collection: str, conditions: list[Condition]) -> int:
        rows = await self.query(collection, Query(conditions=conditions))
        for row in rows:
            await self.delete(collection, row["id"])
        return len(rows)

    async def health(self) -> bool:
        return True

    async def close(self) -> None:
        return None
