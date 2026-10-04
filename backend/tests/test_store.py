"""The store contract: both implementations must behave identically here."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import ConflictError, NotFoundError
from app.database.base import Op, Query, Sort, Store, eq
from app.database.memory import MemoryStore
from app.schemas.common import utcnow


@pytest.fixture()
def store() -> Store:
    return MemoryStore(None)


async def test_create_get_update_delete(store: Store) -> None:
    created = await store.create("users", {"email": "a@b.c", "display_name": "A"})
    assert created["id"]
    fetched = await store.get("users", created["id"])
    assert fetched is not None and fetched["email"] == "a@b.c"

    updated = await store.update("users", created["id"], {"display_name": "Ada"})
    assert updated["display_name"] == "Ada"
    assert updated["email"] == "a@b.c", "update must merge, not replace"

    await store.delete("users", created["id"])
    assert await store.get("users", created["id"]) is None


async def test_duplicate_create_conflicts(store: Store) -> None:
    await store.create("users", {"id": "same"}, doc_id="same")
    with pytest.raises(ConflictError):
        await store.create("users", {"id": "same"}, doc_id="same")


async def test_update_missing_document_raises(store: Store) -> None:
    with pytest.raises(NotFoundError):
        await store.update("users", "nope", {"a": 1})


async def test_nested_collection_paths_are_independent(store: Store) -> None:
    await store.create("organizations/org1/buttlrs", {"name": "PR Guardian"})
    await store.create("organizations/org2/buttlrs", {"name": "FinanceBot"})
    first = await store.query("organizations/org1/buttlrs")
    second = await store.query("organizations/org2/buttlrs")
    assert [row["name"] for row in first] == ["PR Guardian"]
    assert [row["name"] for row in second] == ["FinanceBot"]


async def test_query_conditions_sorting_and_paging(store: Store) -> None:
    base = utcnow()
    for index in range(5):
        await store.create(
            "executions",
            {
                "status": "completed" if index % 2 == 0 else "failed",
                "created_at": base - timedelta(minutes=index),
                "attempt": index,
            },
        )
    completed = await store.query(
        "executions", Query(conditions=[eq("status", "completed")], order_by="created_at")
    )
    assert len(completed) == 3
    assert completed[0]["attempt"] == 0, "newest first by default"

    paged = await store.query("executions", Query(order_by="created_at", limit=2, offset=1))
    assert [row["attempt"] for row in paged] == [1, 2]

    ascending = await store.query(
        "executions", Query(order_by="created_at", sort=Sort.ASC, limit=1)
    )
    assert ascending[0]["attempt"] == 4

    greater = await store.query("executions", Query(conditions=[]))
    assert len(greater) == 5
    from app.database.base import Condition

    big = await store.query("executions", Query(conditions=[Condition("attempt", Op.GTE, 3)]))
    assert sorted(row["attempt"] for row in big) == [3, 4]


async def test_array_contains_and_count(store: Store) -> None:
    await store.create("buttlrs", {"tools": ["github.list_pull_requests"], "status": "active"})
    await store.create("buttlrs", {"tools": ["jira.create_issue"], "status": "draft"})
    from app.database.base import Condition

    hits = await store.query(
        "buttlrs",
        Query(conditions=[Condition("tools", Op.ARRAY_CONTAINS, "jira.create_issue")]),
    )
    assert len(hits) == 1
    assert await store.count("buttlrs", [eq("status", "active")]) == 1


async def test_collection_group_spans_organizations(store: Store) -> None:
    await store.create(
        "organizations/org1/members", {"user_id": "u1", "organization_id": "org1"}, doc_id="u1"
    )
    await store.create(
        "organizations/org2/members", {"user_id": "u1", "organization_id": "org2"}, doc_id="u1"
    )
    rows = await store.query_group("members", Query(conditions=[eq("user_id", "u1")]))
    assert {row["organization_id"] for row in rows} == {"org1", "org2"}


async def test_datetimes_survive_file_persistence(tmp_path) -> None:
    path = tmp_path / "store.json"
    store = MemoryStore(path)
    moment = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
    await store.create("executions", {"created_at": moment, "status": "completed"})

    reloaded = MemoryStore(path)
    row = await reloaded.get("executions", (await store.query("executions"))[0]["id"])
    assert isinstance(row["created_at"], datetime)
    assert row["created_at"] == moment


async def test_query_one_and_delete_many(store: Store) -> None:
    await store.create("notifications", {"read": False, "user_id": "u1"})
    await store.create("notifications", {"read": True, "user_id": "u1"})
    found = await store.query_one("notifications", [eq("read", True)])
    assert found is not None and found["read"] is True
    removed = await store.delete_many("notifications", [eq("user_id", "u1")])
    assert removed == 2
    assert await store.count("notifications") == 0
