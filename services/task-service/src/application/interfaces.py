from abc import ABC, abstractmethod
from uuid import UUID
from src.domain.entities import Task, Sprint, OutboxEvent

class ITaskRepository(ABC):
    @abstractmethod
    async def save_with_outbox(self, task: Task, event: OutboxEvent | None) -> None:
        pass

    @abstractmethod
    async def get_by_id(self, task_id: UUID) -> Task | None:
        pass

class ISprintRepository(ABC):
    @abstractmethod
    async def save_with_outbox(self, sprint: Sprint, event: OutboxEvent | None) -> None:
        pass

    @abstractmethod
    async def get_by_id(self, sprint_id: UUID) -> Sprint | None:
        pass

class IWorkspaceClient(ABC):
    @abstractmethod
    async def verify_access(self, project_id: str, user_id: str) -> bool:
        pass

class ICacheService(ABC):
    @abstractmethod
    async def get(self, key: str) -> str | None:
        pass

    @abstractmethod
    async def set(self, key: str, value: str, ttl: int = 300) -> None:
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        pass

    @abstractmethod
    async def is_token_blacklisted(self, token: str) -> bool:
        pass
