from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4
import json

class TaskStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"

class SprintStatus(str, Enum):
    PLANNED = "PLANNED"
    PENDING_START = "PENDING_START"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"

@dataclass
class OutboxEvent:
    id: UUID
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: str
    processed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def create(aggregate_type: str, aggregate_id: str, event_type: str, payload: dict) -> "OutboxEvent":
        enriched = {"event_id": str(uuid4()), **payload}
        return OutboxEvent(
            id=uuid4(),
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=json.dumps(enriched),
        )

@dataclass
class Comment:
    id: UUID
    task_id: UUID
    author_id: UUID
    body: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class Board:
    id: UUID
    project_id: UUID
    name: str
    columns: list[str] = field(default_factory=lambda: ["TODO", "IN_PROGRESS", "DONE"])

@dataclass
class Task:
    id: UUID
    project_id: UUID
    title: str
    description: str
    assignee_id: UUID | None
    status: TaskStatus = TaskStatus.TODO
    sprint_id: UUID | None = None

    def change_status(self, new_status: TaskStatus) -> OutboxEvent:
        old_status = self.status
        self.status = new_status
        return OutboxEvent.create(
            aggregate_type="Task",
            aggregate_id=str(self.id),
            event_type="TaskStatusChanged",
            payload={
                "task_id": str(self.id),
                "project_id": str(self.project_id),
                "old_status": old_status.value,
                "new_status": new_status.value,
            },
        )

@dataclass
class Sprint:
    id: UUID
    project_id: UUID
    name: str
    status: SprintStatus = SprintStatus.PLANNED

    def initiate_start(self) -> OutboxEvent:
        if self.status != SprintStatus.PLANNED:
            raise ValueError("Only PLANNED sprints can be started")
        self.status = SprintStatus.PENDING_START
        return OutboxEvent.create(
            aggregate_type="SprintSaga",
            aggregate_id=str(self.id),
            event_type="RESERVE_SPRINT_QUOTA",
            payload={
                "command": "RESERVE_SPRINT_QUOTA",
                "sprint_id": str(self.id),
                "project_id": str(self.project_id),
            },
        )

    def complete_start(self) -> OutboxEvent:
        self.status = SprintStatus.ACTIVE
        return OutboxEvent.create(
            aggregate_type="Sprint",
            aggregate_id=str(self.id),
            event_type="SprintStarted",
            payload={"sprint_id": str(self.id), "project_id": str(self.project_id), "status": "ACTIVE"},
        )

    def compensate_start(self) -> None:
        self.status = SprintStatus.PLANNED
