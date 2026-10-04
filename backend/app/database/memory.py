"""In-memory document store with optional JSON persistence.

This is a production code path, not test scaffolding: Buttlr boots with no cloud account in
development and demo environments, and the whole product must work end to end there. It
implements the same ``Store`` contract as Firestore, including nested collection paths
(``organizations/{id}/buttlrs``) and collection-group queries.

Documents are kept as plain JSON-safe values: ``datetime`` becomes a tagged object, enums
become their values. Services load them back through Pydantic, which coerces both.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.core.logging import get_logger
from app.database.base import Condition, Op, Query, Sort, Store, new_id

logger = get_logger(__name__)

_DT_TAG = "__buttlr_datetime__"


def encode_value(value: Any) -> Any:
    """Normalise a stored value into something JSON/Firestore can hold."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return {_DT_TAG: value.isoformat()}
    if isinstance(value, BaseModel):
        return encode_value(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(k): encode_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [encode_value(v) for v in value]
    return value


def decode_value(value: Any) -> Any:
    if isinstance(value, dict):
        if _DT_TAG in value and len(value) == 1:
            raw = value[_DT_TAG]
            try:
                return datetime.fromisoformat(raw)
            except (TypeError, ValueError):
                return raw
        return {k: decode_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode_value(v) for v in value]
    return value


def _merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        existing = out.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            out[key] = _merge(existing, value)
        else:
            out[key] = value
    return out


def _comparable(value: Any) -> tuple[int, Any]:
    if value is None:
        return (2, "")
    if isinstance(value, bool):
        return (0, float(value))
    if isinstance(value, (int, float)):
        return (0, float(value))
    if isinstance(value, datetime):
        return (0, value.timestamp())
    return (1, str(value))


class MemoryStore(Store):
    """Dict-of-dicts store keyed by collection path, persisted to a JSON file."""

    backend = "memory"

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self._path = Path(path) if path else None
        self._data: dict[str, dict[str, dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        if self._path and self._path.exists():
            self._load()

    # ---- persistence ------------------------------------------------------

    def _load(self) -> None:
        assert self._path is not None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("could not read store file %s: %s", self._path, exc)
            return
        self._data = {
            collection: {doc_id: decode_value(doc) for doc_id, doc in docs.items()}
            for collection, docs in raw.items()
        }
        logger.info(
            "loaded memory store: %d collections from %s", len(self._data), self._path
        )

    def _persist_sync(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = json.dumps(encode_value(self._data))
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self._path)

    async def _flush(self) -> None:
        if self._path is None:
            return
        await asyncio.to_thread(self._persist_sync)

    # ---- helpers ----------------------------------------------------------

    def _collection(self, collection: str) -> dict[str, dict[str, Any]]:
        return self._data.setdefault(collection, {})

    @staticmethod
    def _matches(doc: dict[str, Any], condition: Condition) -> bool:
        actual = doc.get(condition.field)
        expected = condition.value
        op = condition.op
        if op == Op.EQ:
            return actual == expected
        if op == Op.NE:
            return actual != expected
        if op == Op.IN:
            return actual in (expected or [])
        if op == Op.NOT_IN:
            return actual not in (expected or [])
        if op == Op.ARRAY_CONTAINS:
            return isinstance(actual, list) and expected in actual
        if op == Op.ARRAY_CONTAINS_ANY:
            if not isinstance(actual, list):
                return False
            return any(item in actual for item in (expected or []))
        left, right = _comparable(actual), _comparable(expected)
        if op == Op.GT:
            return left > right
        if op == Op.GTE:
            return left >= right
        if op == Op.LT:
            return left < right
        if op == Op.LTE:
            return left <= right
        return False

    def _select(self, collection: str, query: Query | None) -> list[dict[str, Any]]:
        query = query or Query()
        rows = [
            doc
            for doc in self._collection(collection).values()
            if all(self._matches(doc, condition) for condition in query.conditions)
        ]
        if query.order_by:
            rows.sort(
                key=lambda doc: _comparable(doc.get(query.order_by)),  # type: ignore[arg-type]
                reverse=query.sort == Sort.DESC,
            )
        else:
            rows.sort(key=lambda doc: str(doc.get("id", "")), reverse=query.sort == Sort.DESC)
        if query.offset:
            rows = rows[query.offset :]
        if query.limit is not None:
            rows = rows[: query.limit]
        return [dict(row) for row in rows]

    # ---- Store API --------------------------------------------------------

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        doc = self._collection(collection).get(doc_id)
        return dict(doc) if doc is not None else None

    async def create(
        self, collection: str, data: dict[str, Any], doc_id: str | None = None
    ) -> dict[str, Any]:
        async with self._lock:
            target = self._collection(collection)
            identifier = doc_id or data.get("id") or new_id()
            if identifier in target:
                from app.core.errors import ConflictError

                raise ConflictError(f"A document with id '{identifier}' already exists.")
            payload = {**data, "id": identifier}
            target[identifier] = payload
            await self._flush()
            return dict(payload)

    async def set(
        self, collection: str, doc_id: str, data: dict[str, Any], merge: bool = True
    ) -> dict[str, Any]:
        async with self._lock:
            target = self._collection(collection)
            payload = dict(data)
            existing = target.get(doc_id)
            if merge and existing is not None:
                payload = _merge(existing, payload)
            payload["id"] = doc_id
            target[doc_id] = payload
            await self._flush()
            return dict(payload)

    async def update(
        self, collection: str, doc_id: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        async with self._lock:
            target = self._collection(collection)
            existing = target.get(doc_id)
            if existing is None:
                from app.core.errors import NotFoundError

                raise NotFoundError(f"Document '{doc_id}' not found in '{collection}'.")
            merged = _merge(existing, patch)
            merged["id"] = doc_id
            target[doc_id] = merged
            await self._flush()
            return dict(merged)

    async def delete(self, collection: str, doc_id: str) -> None:
        async with self._lock:
            self._collection(collection).pop(doc_id, None)
            await self._flush()

    async def query(self, collection: str, query: Query | None = None) -> list[dict[str, Any]]:
        return self._select(collection, query)

    async def count(
        self, collection: str, conditions: list[Condition] | None = None
    ) -> int:
        return len(self._select(collection, Query(conditions=conditions or [])))

    async def query_group(
        self, collection_group: str, query: Query | None = None
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in list(self._data):
            if path.split("/")[-1] == collection_group:
                rows.extend(self._select(path, query))
        query = query or Query()
        if query.order_by:
            rows.sort(
                key=lambda doc: _comparable(doc.get(query.order_by)),  # type: ignore[arg-type]
                reverse=query.sort == Sort.DESC,
            )
        if query.limit is not None:
            rows = rows[: query.limit]
        return rows

    async def delete_many(self, collection: str, conditions: list[Condition]) -> int:
        rows = await self.query(collection, Query(conditions=conditions))
        for row in rows:
            await self.delete(collection, row["id"])
        return len(rows)

    async def health(self) -> bool:
        return True

    def dump(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Test/diagnostic helper: the raw store contents."""
        return {collection: dict(docs) for collection, docs in self._data.items()}
