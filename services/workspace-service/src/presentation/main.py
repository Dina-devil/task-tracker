import asyncio
from contextlib import asynccontextmanager
import json
import os
from uuid import UUID
import grpc
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import aio_pika

import workspace_pb2
import workspace_pb2_grpc
from src.infrastructure.database import Base, PostgresProjectRepository
from src.application.use_cases import CreateProjectUseCase, CheckProjectAccessUseCase, ReserveSprintQuotaUseCase

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@postgres:5432/workspace_db")
RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@rabbitmq:5672/")

engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class WorkspaceGrpcServicer(workspace_pb2_grpc.WorkspaceServiceServicer):
    async def CheckProjectAccess(self, request, context):
        try:
            proj_uuid = UUID(request.project_id)
            user_uuid = UUID(request.user_id)
        except ValueError:
            return workspace_pb2.ProjectAccessResponse(has_access=False, organization_id="")

        async with SessionLocal() as session:
            repo = PostgresProjectRepository(session)
            uc = CheckProjectAccessUseCase(repo)
            ok, org_id = await uc.execute(proj_uuid, user_uuid)
            return workspace_pb2.ProjectAccessResponse(has_access=ok, organization_id=org_id)

async def serve_grpc():
    server = grpc.aio.server()
    workspace_pb2_grpc.add_WorkspaceServiceServicer_to_server(WorkspaceGrpcServicer(), server)
    server.add_insecure_port("[::]:50051")
    await server.start()
    await server.wait_for_termination()

async def consume_saga_commands():
    connection = await aio_pika.connect_robust(RABBIT_URL)
    channel = await connection.channel()
    queue = await channel.declare_queue("workspace.quota.commands", durable=True)
    exchange = await channel.declare_exchange("saga.events", aio_pika.ExchangeType.TOPIC, durable=True)

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process():
                payload = json.loads(message.body.decode())
                if payload.get("command") == "RESERVE_SPRINT_QUOTA":
                    async with SessionLocal() as session:
                        repo = PostgresProjectRepository(session)
                        uc = ReserveSprintQuotaUseCase(repo)
                        reserved = await uc.execute(UUID(payload["project_id"]))
                        reply = {
                            "event": "QUOTA_RESERVED" if reserved else "QUOTA_EXCEEDED",
                            "sprint_id": payload["sprint_id"],
                        }
                        await exchange.publish(
                            aio_pika.Message(body=json.dumps(reply).encode()),
                            routing_key="saga.sprint.replies",
                        )

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    grpc_task = asyncio.create_task(serve_grpc())
    saga_task = asyncio.create_task(consume_saga_commands())
    try:
        yield
    finally:
        grpc_task.cancel()
        saga_task.cancel()
        await engine.dispose()

app = FastAPI(title="Workspace Service", lifespan=lifespan)

class CreateProjectRequest(BaseModel):
    organization_id: UUID
    name: str
    owner_id: UUID
    max_active_sprints: int = 1
    team_id: UUID | None = None

@app.post("/projects", status_code=201)
async def create_project(req: CreateProjectRequest):
    async with SessionLocal() as session:
        repo = PostgresProjectRepository(session)
        uc = CreateProjectUseCase(repo)
        proj = await uc.execute(req.organization_id, req.name, req.owner_id, req.max_active_sprints, req.team_id)
        return {"id": str(proj.id), "name": proj.name, "max_active_sprints": proj.max_active_sprints}
