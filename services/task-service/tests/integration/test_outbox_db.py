import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4
import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from src.application.use_cases import StartSprintSagaOrchestrator
from src.domain.entities import OutboxEvent, Sprint, SprintStatus, Task, TaskStatus
from src.infrastructure.database import ( Base, OutboxModel, PostgresSprintRepository, PostgresTaskRepository, SprintModel, TaskModel)
from src.presentation.api import JWT_SECRET, app

TEST_DB_URL = os.getenv("TEST_TASK_DB_URL", os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/task_db"))

def _make_jwt(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.mark.asyncio
async def test_atomic_save_task_and_outbox_with_rollback():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)

    # 1. Успешная запись задачи и outbox
    task_id = uuid4()
    task = Task(
        id=task_id,
        project_id=uuid4(),
        title="Test Outbox",
        description="Desc",
        assignee_id=None,
    )
    event = task.change_status(TaskStatus.IN_PROGRESS)

    async with Session() as session:
        repo = PostgresTaskRepository(session)
        await repo.save_with_outbox(task, event)

    async with Session() as session:
        saved_task = (
            await session.execute(select(TaskModel).where(TaskModel.id == str(task_id)))
        ).scalar_one()
        saved_outbox = (
            await session.execute(
                select(OutboxModel).where(OutboxModel.aggregate_id == str(task_id))
            )
        ).scalar_one()

        assert saved_task.status == "IN_PROGRESS"
        assert saved_outbox.event_type == "TaskStatusChanged"
        assert saved_outbox.processed is False

    # 2. Ошибка при добавлении в outbox -> задача не сохраняется
    fail_task_id = uuid4()
    fail_task = Task(
        id=fail_task_id,
        project_id=uuid4(),
        title="Should Rollback",
        description="Desc",
        assignee_id=None,
    )
    fail_event = OutboxEvent.create("Task", str(fail_task_id), "TaskCreated", {"task_id": str(fail_task_id)})

    async with Session() as session:
        repo = PostgresTaskRepository(session)
        orig_add = session.add

        def fail_on_outbox(obj):
            if isinstance(obj, OutboxModel):
                raise RuntimeError("Outbox write error")
            return orig_add(obj)

        with patch.object(session, "add", side_effect=fail_on_outbox):
            with pytest.raises(RuntimeError):
                await repo.save_with_outbox(fail_task, fail_event)
            await session.rollback()

    async with Session() as session:
        missing = (
            await session.execute(select(TaskModel).where(TaskModel.id == str(fail_task_id)))
        ).scalar_one_or_none()
        assert missing is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_sprint_saga_and_http_api():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    user_id = str(uuid4())
    project_id = str(uuid4())
    token = _make_jwt(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    cache_mock = AsyncMock()
    cache_mock.is_token_blacklisted = AsyncMock(return_value=False)
    cache_mock.get = AsyncMock(return_value=None)
    cache_mock.set = AsyncMock(return_value=None)
    cache_mock.delete = AsyncMock(return_value=None)
    cache_mock.close = AsyncMock(return_value=None)

    workspace_mock = AsyncMock()
    workspace_mock.verify_access = AsyncMock(return_value=True)

    with (
        patch("src.presentation.api.SessionLocal", TestSessionLocal),
        patch("src.presentation.api.cache_service", cache_mock),
        patch("src.presentation.api.workspace_client", workspace_mock),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Создание задачи
            create_res = await client.post(
                "/tasks",
                headers=headers,
                json={
                    "project_id": project_id,
                    "title": "API Task",
                    "description": "Integration check",
                },
            )
            assert create_res.status_code == 201
            task_id = create_res.json()["id"]

            # 2. Получение задачи
            get_res = await client.get(f"/tasks/{task_id}", headers=headers)
            assert get_res.status_code == 200
            assert get_res.json()["title"] == "API Task"

            # 3. Обновление статуса задачи
            patch_res = await client.patch(
                f"/tasks/{task_id}/status",
                headers=headers,
                json={"status": "DONE"},
            )
            assert patch_res.status_code == 200
            assert patch_res.json()["status"] == "DONE"

            # 4. Создание и запуск саги спринта
            sprint_res = await client.post(
                "/sprints",
                headers=headers,
                json={"project_id": project_id, "name": "Sprint Integration"},
            )
            assert sprint_res.status_code == 201
            sprint_id = sprint_res.json()["id"]

            start_res = await client.post(f"/sprints/{sprint_id}/start", headers=headers)
            assert start_res.status_code == 200
            assert start_res.json()["status"] == "PENDING_START"

            # 5. Отозванный токен -> 401
            cache_mock.is_token_blacklisted.return_value = True
            revoked_res = await client.get(f"/tasks/{task_id}", headers=headers)
            assert revoked_res.status_code == 401

    # Проверяем состояние спринта в БД при компенсации
    async with TestSessionLocal() as session:
        repo = PostgresSprintRepository(session)
        orchestrator = StartSprintSagaOrchestrator(repo)
        await orchestrator.handle_saga_reply(sprint_id.__class__(sprint_id), "QUOTA_EXCEEDED")

    async with TestSessionLocal() as session:
        s_row = (
            await session.execute(select(SprintModel).where(SprintModel.id == sprint_id))
        ).scalar_one()
        assert s_row.status == SprintStatus.PLANNED.value

    await engine.dispose()