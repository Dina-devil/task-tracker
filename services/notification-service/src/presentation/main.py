import asyncio
from contextlib import asynccontextmanager
import json
import os
from uuid import uuid4
import aio_pika
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from src.application.use_cases import ProcessDomainEventInboxUseCase
from src.infrastructure.database import Base, NotificationModel, PostgresInboxNotificationStore

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@postgres:5432/notification_db")
RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@rabbitmq:5672/")

engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def consume_domain_events():
    while True:
        try:
            connection = await aio_pika.connect_robust(RABBIT_URL)
            async with connection:
                channel = await connection.channel()
                exchange = await channel.declare_exchange("domain.events", aio_pika.ExchangeType.TOPIC, durable=True)
                queue = await channel.declare_queue("notifications.domain.events", durable=True)
                await queue.bind(exchange, routing_key="task.#")

                async with queue.iterator() as queue_iter:
                    async for message in queue_iter:
                        async with message.process():
                            raw = message.body.decode()
                            try:
                                payload = json.loads(raw)
                                event_id = str(payload.get("event_id") or payload.get("id") or uuid4())
                            except Exception:
                                event_id = str(uuid4())
                            async with SessionLocal() as session:
                                store = PostgresInboxNotificationStore(session)
                                uc = ProcessDomainEventInboxUseCase(store)
                                await uc.execute(event_id, raw)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Notification consumer error: {e}")
            await asyncio.sleep(2)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    consumer_task = asyncio.create_task(consume_domain_events())
    try:
        yield
    finally:
        consumer_task.cancel()
        await asyncio.gather(consumer_task, return_exceptions=True)
        await engine.dispose()

app = FastAPI(title="Notification Service", lifespan=lifespan)

@app.get("/notifications")
async def list_notifications():
    async with SessionLocal() as session:
        res = await session.execute(select(NotificationModel))
        return [{"id": n.id, "message": n.message} for n in res.scalars().all()]
