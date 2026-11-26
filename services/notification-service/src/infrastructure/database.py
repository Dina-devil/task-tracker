from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import select
from src.application.interfaces import IInboxNotificationStore

class Base(DeclarativeBase):
    pass

class InboxMessageModel(Base):
    __tablename__ = "inbox_messages"
    event_id: Mapped[str] = mapped_column(primary_key=True)
    processed_at: Mapped[datetime]

class NotificationModel(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(primary_key=True)
    message: Mapped[str]
    created_at: Mapped[datetime]

class PostgresInboxNotificationStore(IInboxNotificationStore):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_idempotently(self, event_id: str, message: str) -> bool:
        async with self.session.begin():
            exists = await self.session.execute(
                select(InboxMessageModel).where(InboxMessageModel.event_id == event_id)
            )
            if exists.scalar_one_or_none():
                return False
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            self.session.add(InboxMessageModel(event_id=event_id, processed_at=now))
            self.session.add(NotificationModel(id=str(uuid4()), message=message, created_at=now))
            return True
