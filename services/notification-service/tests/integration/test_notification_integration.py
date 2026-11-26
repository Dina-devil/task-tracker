import os
from unittest.mock import patch
from uuid import uuid4
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from src.application.use_cases import ProcessDomainEventInboxUseCase
from src.infrastructure.database import (Base, InboxMessageModel, NotificationModel, PostgresInboxNotificationStore)
from src.presentation.main import app

TEST_DB_URL = os.getenv("TEST_NOTIFICATION_DB_URL", os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/notification_db"))

@pytest.mark.asyncio
async def test_postgres_inbox_idempotency_and_get_notifications():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    event_id = f"evt-{uuid4()}"
    payload_json = '{"task_id":"42","event":"TaskCreated"}'

    async with TestSessionLocal() as session:
        store = PostgresInboxNotificationStore(session)
        uc = ProcessDomainEventInboxUseCase(store)
        created = await uc.execute(event_id, payload_json)
        assert created is True

    async with TestSessionLocal() as session:
        store = PostgresInboxNotificationStore(session)
        uc = ProcessDomainEventInboxUseCase(store)
        duplicate = await uc.execute(event_id, payload_json)
        assert duplicate is False

    async with TestSessionLocal() as session:
        inbox_rows = (
            await session.execute(
                select(InboxMessageModel).where(InboxMessageModel.event_id == event_id)
            )
        ).scalars().all()
        notif_rows = (
            await session.execute(
                select(NotificationModel).where(
                    NotificationModel.message == f"Event processed: {payload_json}"
                )
            )
        ).scalars().all()

        assert len(inbox_rows) == 1
        assert len(notif_rows) == 1

    with patch("src.presentation.main.SessionLocal", TestSessionLocal):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/notifications")
            assert res.status_code == 200
            items = res.json()
            assert any(
                item["message"] == f"Event processed: {payload_json}" for item in items
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_inbox_rollback_on_failure():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    event_id = f"evt-fail-{uuid4()}"
    payload_json = '{"task_id":"99"}'

    async with TestSessionLocal() as session:
        store = PostgresInboxNotificationStore(session)
        uc = ProcessDomainEventInboxUseCase(store)
        orig_add = session.add

        def fail_on_notification(obj):
            if isinstance(obj, NotificationModel):
                raise RuntimeError("Simulated notification insert failure")
            return orig_add(obj)

        with patch.object(session, "add", side_effect=fail_on_notification):
            with pytest.raises(RuntimeError):
                await uc.execute(event_id, payload_json)

    async with TestSessionLocal() as session:
        inbox_row = (
            await session.execute(
                select(InboxMessageModel).where(InboxMessageModel.event_id == event_id)
            )
        ).scalar_one_or_none()
        assert inbox_row is None

    async with TestSessionLocal() as session:
        store = PostgresInboxNotificationStore(session)
        uc = ProcessDomainEventInboxUseCase(store)
        assert await uc.execute(event_id, payload_json) is True

    await engine.dispose()