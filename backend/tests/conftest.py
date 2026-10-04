"""Test configuration.

Runs entirely offline: dev auth, in-memory store, scheduler off. No test touches the network.
"""

from __future__ import annotations

import os
import tempfile

# Pinned explicitly (not setdefault): a developer's own backend/.env must never change what the
# suite exercises, and environment variables take precedence over the dotenv file.
os.environ["AUTH_MODE"] = "dev"
os.environ["STORE_BACKEND"] = "memory"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["EXECUTION_WORKERS"] = "2"
os.environ["FIREBASE_PROJECT_ID"] = ""
os.environ["FIREBASE_CREDENTIALS_JSON"] = ""
os.environ["FIREBASE_CREDENTIALS_PATH"] = ""
os.environ["FIRESTORE_EMULATOR_HOST"] = ""
os.environ["GITHUB_OAUTH_CLIENT_ID"] = ""
os.environ["GITHUB_OAUTH_CLIENT_SECRET"] = ""
os.environ["GOOGLE_OAUTH_CLIENT_ID"] = ""
os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = ""
# Model providers too: a developer's own keys must not change what the suite asserts, and a
# test must never spend someone's credits.
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["GOOGLE_API_KEY"] = ""
os.environ["OLLAMA_BASE_URL"] = ""
os.environ["MEMORY_STORE_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="buttlr-test-"), "store.json"
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
