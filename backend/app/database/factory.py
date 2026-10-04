"""Store selection.

``STORE_BACKEND=auto`` picks Firestore when Firebase is configured and the memory store
otherwise, so the same code runs locally, in CI and in production.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.logging import get_logger
from app.database.base import Store

logger = get_logger(__name__)


def build_store(settings: Settings) -> Store:
    backend = settings.resolved_store_backend
    if backend == "firestore":
        from app.database.firestore import FirestoreStore

        logger.info("using Firestore store (project=%s)", settings.firebase_project_id or "default")
        return FirestoreStore(settings)

    from app.database.memory import MemoryStore

    logger.info("using in-memory store at %s", settings.memory_store_path)
    return MemoryStore(settings.memory_store_path)


__all__ = ["build_store"]
