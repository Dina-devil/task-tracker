import asyncio
from contextlib import asynccontextmanager
import os
from uuid import UUID, uuid4
import jwt
from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.domain.entities import Sprint, TaskStatus
from src.infrastructure.database import Base, PostgresTaskRepository, PostgresSprintRepository
from src.infrastructure.adapters import GrpcWorkspaceClient, RedisCacheService
from src.infrastructure.outbox_relay import run_outbox_relay, run_saga_reply_listener
from src.application.use_cases import (
    CreateTaskUseCase,
    GetTaskUseCase,
    UpdateTaskStatusUseCase,
    StartSprintSagaOrchestrator,
)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@postgres:5432/task_db")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/1")
AUTH_REDIS_URL = os.getenv("AUTH_REDIS_URL", "redis://redis:6379/0")
RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@rabbitmq:5672/")
WORKSPACE_GRPC = os.getenv("WORKSPACE_GRPC", "workspace-service:50051")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-jwt-key-change-in-prod")

engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
cache_service = RedisCacheService(REDIS_URL, AUTH_REDIS_URL)
workspace_client = GrpcWorkspaceClient(WORKSPACE_GRPC)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    relay_task = asyncio.create_task(run_outbox_relay(SessionLocal, RABBIT_URL))
    saga_task = asyncio.create_task(run_saga_reply_listener(SessionLocal, RABBIT_URL))
    try:
        yield
    finally:
        relay_task.cancel()
        saga_task.cancel()
        await cache_service.close()
        await engine.dispose()

app = FastAPI(title="Task Service", lifespan=lifespan)

async def get_current_user_id(authorization: str = Header(...)) -> str:
    try:
        token = authorization.replace("Bearer ", "").strip()
        if await cache_service.is_token_blacklisted(token):
            raise HTTPException(status_code=401, detail="Token has been revoked")
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload["sub"]
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired JWT token")

class CreateTaskBody(BaseModel):
    project_id: UUID
    title: str
    description: str

class UpdateStatusBody(BaseModel):
    status: TaskStatus

@app.post("/tasks", status_code=201)
async def create_task(body: CreateTaskBody, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as session:
        repo = PostgresTaskRepository(session)
        uc = CreateTaskUseCase(repo, workspace_client)
        try:
            task = await uc.execute(body.project_id, user_id, body.title, body.description)
            return {"id": str(task.id), "title": task.title, "status": task.status.value}
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))

@app.patch("/tasks/{task_id}/status")
async def update_task_status(task_id: UUID, body: UpdateStatusBody, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as session:
        repo = PostgresTaskRepository(session)
        uc = UpdateTaskStatusUseCase(repo, cache_service)
        try:
            task = await uc.execute(task_id, body.status)
            return {"id": str(task.id), "status": task.status.value}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

@app.get("/tasks/{task_id}")
async def get_task(task_id: UUID, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as session:
        repo = PostgresTaskRepository(session)
        uc = GetTaskUseCase(repo, cache_service)
        task = await uc.execute(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

class CreateSprintBody(BaseModel):
    project_id: UUID
    name: str

@app.post("/sprints", status_code=201)
async def create_sprint(body: CreateSprintBody, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as session:
        repo = PostgresSprintRepository(session)
        sprint = Sprint(id=uuid4(), project_id=body.project_id, name=body.name)
        await repo.save_with_outbox(sprint, None)
        return {"id": str(sprint.id), "status": sprint.status.value}

@app.post("/sprints/{sprint_id}/start")
async def start_sprint(sprint_id: UUID, user_id: str = Depends(get_current_user_id)):
    async with SessionLocal() as session:
        repo = PostgresSprintRepository(session)
        orchestrator = StartSprintSagaOrchestrator(repo)
        sprint = await orchestrator.start_sprint(sprint_id)
        return {"id": str(sprint.id), "status": sprint.status.value, "message": "Saga initiated"}
