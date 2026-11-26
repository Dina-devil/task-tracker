import asyncio
import json
from uuid import UUID
import aio_pika
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from src.infrastructure.database import OutboxModel, PostgresSprintRepository
from src.application.use_cases import StartSprintSagaOrchestrator

async def run_outbox_relay(session_factory: async_sessionmaker, rabbit_url: str):
    connection = await aio_pika.connect_robust(rabbit_url)
    channel = await connection.channel()
    events_exchange = await channel.declare_exchange("domain.events", aio_pika.ExchangeType.TOPIC, durable=True)
    await channel.declare_queue("workspace.quota.commands", durable=True)

    while True:
        try:
            async with session_factory() as session:
                async with session.begin():
                    stmt = (
                        select(OutboxModel)
                        .where(OutboxModel.processed == False)
                        .limit(50)
                        .with_for_update(skip_locked=True)
                    )
                    res = await session.execute(stmt)
                    messages = res.scalars().all()

                    for msg in messages:
                        if msg.aggregate_type == "SprintSaga":
                            await channel.default_exchange.publish(
                                aio_pika.Message(body=msg.payload.encode(), delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                                routing_key="workspace.quota.commands",
                            )
                        else:
                            await events_exchange.publish(
                                aio_pika.Message(body=msg.payload.encode(), delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                                routing_key=f"task.{msg.event_type.lower()}",
                            )
                        msg.processed = True
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Outbox relay error: {e}")
        await asyncio.sleep(1)

async def run_saga_reply_listener(session_factory: async_sessionmaker, rabbit_url: str):
    connection = await aio_pika.connect_robust(rabbit_url)
    channel = await connection.channel()
    exchange = await channel.declare_exchange("saga.events", aio_pika.ExchangeType.TOPIC, durable=True)
    queue = await channel.declare_queue("task.sprint.saga.replies", durable=True)
    await queue.bind(exchange, routing_key="saga.sprint.replies")

    try:
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    data = json.loads(message.body.decode())
                    async with session_factory() as session:
                        repo = PostgresSprintRepository(session)
                        orchestrator = StartSprintSagaOrchestrator(repo)
                        await orchestrator.handle_saga_reply(UUID(data["sprint_id"]), data["event"])
    except asyncio.CancelledError:
        pass
