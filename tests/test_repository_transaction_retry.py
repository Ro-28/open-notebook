"""Aborted database operations retry, never whole upload workflows."""

import asyncio
from collections import Counter
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from open_notebook.database import repository

CONFLICT = (
    "The query was not executed due to a failed transaction. "
    "Failed to commit transaction due to a read or write conflict. "
    "This transaction can be retried."
)


@pytest.fixture
def connection(monkeypatch):
    db = AsyncMock()

    @asynccontextmanager
    async def connect():
        yield db

    monkeypatch.setattr(repository, "db_connection", connect)
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [CONFLICT, RuntimeError(CONFLICT)])
async def test_create_retries_explicitly_aborted_insert(connection, error):
    connection.insert.side_effect = [error, [{"id": "source:one"}]]
    result = await repository.repo_create("source", {"title": "one"})
    assert result == [{"id": "source:one"}]
    assert connection.insert.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["relate", "update", "upsert", "insert"])
async def test_atomic_writes_retry_aborted_statement(connection, kind):
    connection.query.side_effect = [RuntimeError(CONFLICT), [{"id": "source:one"}]]
    connection.insert.side_effect = [RuntimeError(CONFLICT), [{"id": "source:one"}]]
    if kind == "relate":
        result = await repository.repo_relate("source:one", "reference", "notebook:one")
    elif kind == "update":
        result = await repository.repo_update("source", "source:one", {"title": "one"})
    elif kind == "upsert":
        result = await repository.repo_upsert("source", "source:one", {"title": "one"})
    else:
        result = await repository.repo_insert("source", [{"title": "one"}])
    assert result == [{"id": "source:one"}]
    method = connection.insert if kind == "insert" else connection.query
    assert method.await_count == 2


@pytest.fixture
def retry_wait(monkeypatch):
    wait = AsyncMock()
    monkeypatch.setattr(repository.asyncio, "sleep", wait)
    monkeypatch.setattr(repository.random, "uniform", lambda low, high: high)
    return wait


@pytest.mark.asyncio
async def test_retry_budget_is_five_attempts_with_bounded_backoff(
    connection, retry_wait
):
    error = RuntimeError(CONFLICT)
    connection.insert.side_effect = error
    with pytest.raises(RuntimeError) as caught:
        await repository.repo_create("source", {})
    assert caught.value is error
    assert connection.insert.await_count == 5
    assert [call.args[0] for call in retry_wait.await_args_list] == [
        0.05,
        0.1,
        0.2,
        0.4,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("transaction failed"),
        RuntimeError("record already contains an entry"),
        RuntimeError("permission denied"),
        RuntimeError("conflict with schema"),
        TimeoutError("unknown commit outcome"),
        ConnectionError("connection lost"),
        ValueError(CONFLICT),
    ],
)
async def test_permanent_or_ambiguous_errors_are_not_retried(
    connection, retry_wait, error
):
    connection.insert.side_effect = error
    with pytest.raises(RuntimeError):
        await repository.repo_create("source", {})
    connection.insert.assert_awaited_once()
    retry_wait.assert_not_awaited()


@pytest.mark.asyncio
async def test_arbitrary_query_is_not_replayed(connection, retry_wait):
    connection.query.side_effect = RuntimeError(CONFLICT)
    with pytest.raises(RuntimeError, match="read or write conflict"):
        await repository.repo_query("CREATE source; CREATE source;")
    connection.query.assert_awaited_once()
    retry_wait.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_ignore_behavior_is_preserved(connection, retry_wait):
    connection.insert.side_effect = RuntimeError("record already contains an entry")
    assert await repository.repo_insert("source", [{}], ignore_duplicates=True) == []
    connection.insert.assert_awaited_once()
    retry_wait.assert_not_awaited()


@pytest.mark.asyncio
async def test_success_is_not_replayed_when_connection_cleanup_fails(
    monkeypatch, connection
):
    connection.insert.return_value = [{"id": "source:one"}]

    @asynccontextmanager
    async def connect():
        yield connection
        raise RuntimeError(CONFLICT)

    monkeypatch.setattr(repository, "db_connection", connect)
    with pytest.raises(RuntimeError, match="read or write conflict"):
        await repository.repo_create("source", {})
    connection.insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancellation_during_backoff_stops_retries(connection, retry_wait):
    connection.insert.side_effect = RuntimeError(CONFLICT)
    retry_wait.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await repository.repo_create("source", {})
    connection.insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_inserts_commit_once_per_source(connection):
    attempts = Counter()
    committed = []
    semaphore = asyncio.Semaphore(5)

    async def insert(table, data):
        title = data["title"]
        attempts[title] += 1
        if attempts[title] == 1:
            raise RuntimeError(CONFLICT)
        committed.append(title)
        return [{"id": f"source:{title}"}]

    async def upload(index):
        async with semaphore:
            return await repository.repo_create("source", {"title": str(index)})

    connection.insert.side_effect = insert
    results = await asyncio.gather(*(upload(i) for i in range(10)))
    assert len(results) == 10
    assert len({row[0]["id"] for row in results}) == 10
    assert Counter(committed) == Counter({str(i): 1 for i in range(10)})
    assert attempts == Counter({str(i): 2 for i in range(10)})
