"""Test configuration.

Runs entirely offline: dev auth, in-memory store, scheduler off. No test touches the network.
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("AUTH_MODE", "dev")
os.environ.setdefault("STORE_BACKEND", "memory")
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("EXECUTION_WORKERS", "2")
os.environ.setdefault(
    "MEMORY_STORE_PATH", os.path.join(tempfile.mkdtemp(prefix="buttlr-test-"), "store.json")
)

from collections.abc import Iterator

import pytest

from app.container import Container, set_container
from app.database.memory import MemoryStore


@pytest.fixture()
def container() -> Iterator[Container]:
    """A container with a private, file-less store so tests cannot leak into each other."""
    built = Container(store=MemoryStore(None))
    set_container(built)
    try:
        yield built
    finally:
        set_container(None)


@pytest.fixture()
def client(container: Container):
    from fastapi.testclient import TestClient

    from app.main import app

    app.state.container = container
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def owner_token(client) -> str:
    response = client.post("/api/v1/auth/dev/login", json={"email": "owner@example.com"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
