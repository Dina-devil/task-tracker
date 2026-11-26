import json
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from src.application.use_cases import (CreateTaskUseCase, GetTaskUseCase, StartSprintSagaOrchestrator, UpdateTaskStatusUseCase)
from src.domain.entities import OutboxEvent, Sprint, SprintStatus, Task, TaskStatus


def test_outbox_event_enriches_payload_with_event_id():
    event = OutboxEvent.create(
        aggregate_type="Task",
        aggregate_id="task-1",
        event_type="TaskCreated",
        payload={"task_id": "task-1", "title": "Spec"},
    )
    parsed = json.loads(event.payload)
    assert "event_id" in parsed
    assert parsed["task_id"] == "task-1"
    assert event.processed is False


@pytest.mark.asyncio
async def test_create_task_success_and_access_denied():
    task_repo = AsyncMock()
    workspace_client = AsyncMock()
    workspace_client.verify_access.side_effect = [True, False]

    uc = CreateTaskUseCase(task_repo, workspace_client)
    project_id = uuid4()
    user_id = str(uuid4())

    task = await uc.execute(project_id, user_id, "Implement gRPC", "Details")
    assert task.project_id == project_id
    assert task.assignee_id == uuid4().__class__(user_id)
    assert task.status == TaskStatus.TODO

    task_repo.save_with_outbox.assert_awaited_once()
    saved_task, outbox_ev = task_repo.save_with_outbox.call_args[0]
    assert saved_task.id == task.id
    assert outbox_ev is not None
    assert outbox_ev.event_type == "TaskCreated"

    with pytest.raises(PermissionError):
        await uc.execute(project_id, user_id, "Forbidden Task", "No access")


@pytest.mark.asyncio
async def test_get_task_cache_miss_and_hit():
    task_id = uuid4()
    project_id = uuid4()
    task = Task(
        id=task_id,
        project_id=project_id,
        title="Cache me",
        description="Body",
        assignee_id=None,
        status=TaskStatus.IN_PROGRESS,
    )

    repo = AsyncMock()
    repo.get_by_id.return_value = task
    cache = AsyncMock()
    store = {}

    async def fake_get(key: str):
        return store.get(key)

    async def fake_set(key: str, value: str, ttl: int = 300):
        store[key] = value

    cache.get.side_effect = fake_get
    cache.set.side_effect = fake_set

    uc = GetTaskUseCase(repo, cache)

    first = await uc.execute(task_id)
    assert first is not None
    assert first["title"] == "Cache me"
    assert first["status"] == "IN_PROGRESS"
    repo.get_by_id.assert_awaited_once_with(task_id)
    cache.set.assert_awaited_once()

    second = await uc.execute(task_id)
    assert second == first
    repo.get_by_id.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_task_returns_none_when_missing():
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    cache = AsyncMock()
    cache.get.return_value = None

    uc = GetTaskUseCase(repo, cache)
    assert await uc.execute(uuid4()) is None


@pytest.mark.asyncio
async def test_update_task_status_invalidates_cache_and_writes_outbox():
    task_id = uuid4()
    task = Task(
        id=task_id,
        project_id=uuid4(),
        title="T1",
        description="D1",
        assignee_id=None,
        status=TaskStatus.TODO,
    )
    repo = AsyncMock()
    repo.get_by_id.return_value = task
    cache = AsyncMock()

    uc = UpdateTaskStatusUseCase(repo, cache)
    updated = await uc.execute(task_id, TaskStatus.DONE)

    assert updated.status == TaskStatus.DONE
    cache.delete.assert_awaited_once_with(f"task:{task_id}")
    repo.save_with_outbox.assert_awaited_once()
    _, outbox_ev = repo.save_with_outbox.call_args[0]
    assert outbox_ev.event_type == "TaskStatusChanged"


@pytest.mark.asyncio
async def test_update_task_status_missing_task_raises():
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    cache = AsyncMock()

    uc = UpdateTaskStatusUseCase(repo, cache)
    with pytest.raises(ValueError, match="Task not found"):
        await uc.execute(uuid4(), TaskStatus.DONE)


@pytest.mark.asyncio
async def test_sprint_saga_full_lifecycle_and_compensation():
    sprint_id = uuid4()
    sprint = Sprint(id=sprint_id, project_id=uuid4(), name="Sprint 1")
    repo = AsyncMock()
    repo.get_by_id.return_value = sprint

    saga = StartSprintSagaOrchestrator(repo)

    started_cmd = await saga.start_sprint(sprint_id)
    assert started_cmd.status == SprintStatus.PENDING_START
    _, cmd_event = repo.save_with_outbox.call_args[0]
    assert cmd_event.event_type == "RESERVE_SPRINT_QUOTA"

    with pytest.raises(ValueError, match="Only PLANNED sprints can be started"):
        await saga.start_sprint(sprint_id)

    await saga.handle_saga_reply(sprint_id, "QUOTA_RESERVED")
    assert sprint.status == SprintStatus.ACTIVE
    _, complete_event = repo.save_with_outbox.call_args[0]
    assert complete_event is not None
    assert complete_event.event_type == "SprintStarted"

    sprint.status = SprintStatus.PENDING_START
    await saga.handle_saga_reply(sprint_id, "QUOTA_EXCEEDED")
    assert sprint.status == SprintStatus.PLANNED
