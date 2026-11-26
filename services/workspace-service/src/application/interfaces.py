from abc import ABC, abstractmethod
from uuid import UUID
from src.domain.entities import Project, Organization, Team

class IProjectRepository(ABC):
    @abstractmethod
    async def get_by_id(self, project_id: UUID) -> Project | None:
        pass

    @abstractmethod
    async def save(self, project: Project) -> Project:
        pass

    @abstractmethod
    async def try_reserve_sprint(self, project_id: UUID) -> bool:
        pass
