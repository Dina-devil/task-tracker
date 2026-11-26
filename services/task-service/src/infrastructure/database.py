from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import select
from src.domain.entities import Task, TaskStatus, Sprint, SprintStatus, OutboxEvent
from src.application.interfaces import ITaskRepository, ISprintRepository

class Base(DeclarativeBase):
    pass

class BoardModel(Base):
    __tablename__ = "boards"
    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str]
    name: Mapped[str]

class CommentModel(Base):
    __tablename__ = "comments"
    id: Mapped[str] = mapped_column(primary_key=True)
    task_id: Mapped[str]
    author_id: Mapped[str]
    body: Mapped[str]
    created_at: Mapped[datetime]

class TaskModel(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str]
    title: Mapped[str]
    description: Mapped[str]
    assignee_id: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str]

class SprintModel(Base):
    __tablename__ = "sprints"
    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str]
    name: Mapped[str]
    status: Mapped[str]

class OutboxModel(Base):
    __tablename__ = "outbox_messages"
    id: Mapped[str] = mapped_column(primary_key=True)
    aggregate_type: Mapped[str]
    aggregate_id: Mapped[str]
    event_type: Mapped[str]
    payload: Mapped[str]
    processed: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime]

class PostgresTaskRepository(ITaskRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_with_outbox(self, task: Task, event: OutboxEvent | None) -> None:
        db_task = TaskModel(
            id=str(task.id),
            project_id=str(task.project_id),
            title=task.title,
            description=task.description,
            assignee_id=str(task.assignee_id) if task.assignee_id else None,
            status=task.status.value,
        )
        await self.session.merge(db_task)

        if event:
            created_at = event.created_at.replace(tzinfo=None) if event.created_at.tzinfo else event.created_at
            db_outbox = OutboxModel(
                id=str(event.id),
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                event_type=event.event_type,
                payload=event.payload,
                processed=event.processed,
                created_at=created_at,
            )
            self.session.add(db_outbox)

        await self.session.commit()

    async def get_by_id(self, task_id: UUID) -> Task | None:
        res = await self.session.execute(select(TaskModel).where(TaskModel.id == str(task_id)))
        row = res.scalar_one_or_none()
        if not row:
            return None
        return Task(
            id=UUID(row.id),
            project_id=UUID(row.project_id),
            title=row.title,
            description=row.description,
            assignee_id=UUID(row.assignee_id) if row.assignee_id else None,
            status=TaskStatus(row.status),
        )

class PostgresSprintRepository(ISprintRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_with_outbox(self, sprint: Sprint, event: OutboxEvent | None) -> None:
        db_sprint = SprintModel(
            id=str(sprint.id),
            project_id=str(sprint.project_id),
            name=sprint.name,
            status=sprint.status.value,
        )
        await self.session.merge(db_sprint)

        if event:
            created_at = event.created_at.replace(tzinfo=None) if event.created_at.tzinfo else event.created_at
            db_outbox = OutboxModel(
                id=str(event.id),
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                event_type=event.event_type,
                payload=event.payload,
                processed=event.processed,
                created_at=created_at,
            )
            self.session.add(db_outbox)

        await self.session.commit()

    async def get_by_id(self, sprint_id: UUID) -> Sprint | None:
        res = await self.session.execute(select(SprintModel).where(SprintModel.id == str(sprint_id)))
        row = res.scalar_one_or_none()
        if not row:
            return None
        return Sprint(
            id=UUID(row.id),
            project_id=UUID(row.project_id),
            name=row.name,
            status=SprintStatus(row.status),
        )