import os
from unittest.mock import patch
from uuid import uuid4
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from src.application.use_cases import CheckProjectAccessUseCase, ReserveSprintQuotaUseCase
from src.domain.entities import Project
from src.infrastructure.database import Base, PostgresProjectRepository, ProjectModel
from src.presentation.main import app

TEST_DB_URL = os.getenv("TEST_WORKSPACE_DB_URL", os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/workspace_db"))

@pytest.mark.asyncio
async def test_postgres_project_repository_and_quota_reservation():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    project_id = uuid4()
    org_id = uuid4()
    owner_id = uuid4()

    project = Project(
        id=project_id,
        organization_id=org_id,
        team_id=None,
        name="Quota Project",
        owner_id=owner_id,
        active_sprints_count=0,
        max_active_sprints=1,
    )

    async with Session() as session:
        repo = PostgresProjectRepository(session)
        await repo.save(project)

    async with Session() as session:
        repo = PostgresProjectRepository(session)
        access_uc = CheckProjectAccessUseCase(repo)
        ok, found_org_id = await access_uc.execute(project_id, uuid4())
        assert ok is True
        assert found_org_id == str(org_id)

    async with Session() as session:
        repo = PostgresProjectRepository(session)
        reserve_uc = ReserveSprintQuotaUseCase(repo)
        assert await reserve_uc.execute(project_id) is True

    async with Session() as session:
        repo = PostgresProjectRepository(session)
        reserve_uc = ReserveSprintQuotaUseCase(repo)
        assert await reserve_uc.execute(project_id) is False

    async with Session() as session:
        row = (
            await session.execute(select(ProjectModel).where(ProjectModel.id == str(project_id)))
        ).scalar_one()
        assert row.active_sprints_count == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_workspace_create_project_http_endpoint():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    org_id = str(uuid4())
    owner_id = str(uuid4())

    with patch("src.presentation.main.SessionLocal", TestSessionLocal):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/projects",
                json={
                    "organization_id": org_id,
                    "name": "HTTP Workspace Project",
                    "owner_id": owner_id,
                    "max_active_sprints": 2,
                },
            )
            assert res.status_code == 201
            body = res.json()
            assert body["name"] == "HTTP Workspace Project"
            assert body["max_active_sprints"] == 2
            assert "id" in body

    await engine.dispose()