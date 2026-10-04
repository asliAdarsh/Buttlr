"""Firestore-backed store.

Uses the ``firebase-admin`` SDK (already a dependency) and runs the synchronous client in a
thread so the API stays async. Only this module knows Firestore exists.
"""

from __future__ import annotations

import asyncio
import os
from enum import Enum
from typing import Any

from pydantic import BaseModel

from app.core.config import Settings
from app.core.logging import get_logger
from app.database.base import Condition, Op, Query, Sort, Store, new_id

logger = get_logger(__name__)

_FIELD_UNSET = object()


def _encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BaseModel):
        return _encode(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(k): _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_encode(v) for v in value]
    return value


class FirestoreStore(Store):
    backend = "firestore"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any | None = None
        self._init_lock = asyncio.Lock()

    # ---- client -----------------------------------------------------------

    def _ensure_client_sync(self) -> Any:
        if self._client is not None:
            return self._client
        if self._settings.firestore_emulator_host:
            os.environ.setdefault("FIRESTORE_EMULATOR_HOST", self._settings.firestore_emulator_host)
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            if self._settings.firebase_credentials_json:
                import json

                cred = credentials.Certificate(json.loads(self._settings.firebase_credentials_json))
            elif self._settings.firebase_credentials_path:
                cred = credentials.Certificate(self._settings.firebase_credentials_path)
            else:
                cred = credentials.ApplicationDefault()
            options: dict[str, str] = {}
            if self._settings.firebase_project_id:
                options["projectId"] = self._settings.firebase_project_id
            firebase_admin.initialize_app(cred, options or None)
        self._client = firestore.client()
        return self._client

    async def _client_async(self) -> Any:
        async with self._init_lock:
            if self._client is None:
                self._client = await asyncio.to_thread(self._ensure_client_sync)
        return self._client

    def _collection_sync(self, client: Any, collection: str) -> Any:
        parts = [p for p in collection.split("/") if p]
        ref = client.collection(parts[0])
        index = 1
        while index < len(parts):
            ref = ref.document(parts[index])
            index += 1
            if index < len(parts):
                ref = ref.collection(parts[index])
                index += 1
        return ref

    # ---- Store API --------------------------------------------------------

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        client = await self._client_async()

        def run() -> dict[str, Any] | None:
            snapshot = self._collection_sync(client, collection).document(doc_id).get()
            if not snapshot.exists:
                return None
            return {"id": snapshot.id, **snapshot.to_dict()}

        return await asyncio.to_thread(run)

    async def create(
        self, collection: str, data: dict[str, Any], doc_id: str | None = None
    ) -> dict[str, Any]:
        identifier = doc_id or data.get("id") or new_id()
        return await self.set(collection, identifier, data, merge=False)

    async def set(
        self, collection: str, doc_id: str, data: dict[str, Any], merge: bool = True
    ) -> dict[str, Any]:
        client = await self._client_async()
        payload = _encode({**data, "id": doc_id})

        def run() -> dict[str, Any]:
            ref = self._collection_sync(client, collection).document(doc_id)
            ref.set(payload, merge=merge)
            snapshot = ref.get()
            return {"id": snapshot.id, **snapshot.to_dict()}

        return await asyncio.to_thread(run)

    async def update(
        self, collection: str, doc_id: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        client = await self._client_async()
        payload = _encode(patch)

        def run() -> dict[str, Any]:
            ref = self._collection_sync(client, collection).document(doc_id)
            snapshot = ref.get()
            if not snapshot.exists:
                from app.core.errors import NotFoundError

                raise NotFoundError(f"Document '{doc_id}' not found in '{collection}'.")
            ref.set(payload, merge=True)
            merged = ref.get()
            return {"id": merged.id, **merged.to_dict()}

        return await asyncio.to_thread(run)

    async def delete(self, collection: str, doc_id: str) -> None:
        client = await self._client_async()
        await asyncio.to_thread(
            lambda: self._collection_sync(client, collection).document(doc_id).delete()
        )

    async def query(self, collection: str, query: Query | None = None) -> list[dict[str, Any]]:
        client = await self._client_async()
        query = query or Query()

        def run() -> list[dict[str, Any]]:
            ref: Any = self._collection_sync(client, collection)
            for condition in query.conditions:
                ref = ref.where(
                    filter=_firestore_filter(condition)
                )
            if query.order_by:
                ref = ref.order_by(
                    query.order_by,
                    direction="DESCENDING" if query.sort == Sort.DESC else "ASCENDING",
                )
            if query.offset:
                ref = ref.offset(query.offset)
            if query.limit is not None:
                ref = ref.limit(query.limit)
            return [{"id": doc.id, **doc.to_dict()} for doc in ref.stream()]

        return await asyncio.to_thread(run)

    async def count(
        self, collection: str, conditions: list[Condition] | None = None
    ) -> int:
        client = await self._client_async()

        def run() -> int:
            ref: Any = self._collection_sync(client, collection)
            for condition in conditions or []:
                ref = ref.where(filter=_firestore_filter(condition))
            try:
                result = ref.count().get()
                return int(result[0][0].value)
            except Exception:
                return sum(1 for _ in ref.stream())

        return await asyncio.to_thread(run)

    async def query_group(
        self, collection_group: str, query: Query | None = None
    ) -> list[dict[str, Any]]:
        client = await self._client_async()
        query = query or Query()

        def run() -> list[dict[str, Any]]:
            ref: Any = client.collection_group(collection_group)
            for condition in query.conditions:
                ref = ref.where(filter=_firestore_filter(condition))
            if query.order_by:
                ref = ref.order_by(
                    query.order_by,
                    direction="DESCENDING" if query.sort == Sort.DESC else "ASCENDING",
                )
            if query.limit is not None:
                ref = ref.limit(query.limit)
            return [{"id": doc.id, **doc.to_dict()} for doc in ref.stream()]

        return await asyncio.to_thread(run)

    async def delete_many(self, collection: str, conditions: list[Condition]) -> int:
        rows = await self.query(collection, Query(conditions=conditions))
        for row in rows:
            await self.delete(collection, row["id"])
        return len(rows)

    async def health(self) -> bool:
        client = await self._client_async()
        try:
            await asyncio.to_thread(lambda: list(client.collections()))
            return True
        except Exception as exc:
            logger.error(
                "Firestore is not reachable (%s). Check that the Firestore database exists in "
                "project %s and that this service has credentials for it.",
                exc,
                self._settings.firebase_project_id or "default",
            )
            return False

    async def close(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            await asyncio.to_thread(client.close)


def _firestore_filter(condition: Condition) -> Any:
    """Build a Firestore field filter, preferring the modern API when available."""
    from google.cloud.firestore_v1 import FieldFilter  # type: ignore[import-not-found]

    if condition.op == Op.EQ:
        return FieldFilter(condition.field, "==", condition.value)
    try:
        return FieldFilter(condition.field, condition.op.value, condition.value)
    except ValueError:
        # array_contains / array_contains_any spellings differ across SDK versions.
        mapping = {
            Op.ARRAY_CONTAINS: "array_contains",
            Op.ARRAY_CONTAINS_ANY: "array_contains_any",
        }
        return FieldFilter(condition.field, mapping[condition.op], condition.value)


__all__ = ["FirestoreStore"]
