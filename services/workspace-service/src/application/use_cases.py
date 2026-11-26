from uuid import UUID, uuid4
from src.domain.entities import Project
from src.application.interfaces import IProjectRepository

class CreateProjectUseCase:
    def __init__(self, repo: IProjectRepository):
        self.repo = repo

    async def execute(self, organization_id: UUID, name: str, owner_id: UUID, max_active_sprints: int = 1, team_id: UUID | None = None) -> Project:
        project = Project(
            id=uuid4(),
            organization_id=organization_id,
            team_id=team_id,
            name=name,
            owner_id=owner_id,
            active_sprints_count=0,
            max_active_sprints=max_active_sprints,
        )
        return await self.repo.save(project)

class CheckProjectAccessUseCase:
    def __init__(self, repo: IProjectRepository):
        self.repo = repo

    async def execute(self, project_id: UUID, user_id: UUID) -> tuple[bool, str]:
        project = await self.repo.get_by_id(project_id)
        if not project:
            return False, ""
        # Разрешаем доступ владельцу или любому участнику в рамках учебного прототипа
        return True, str(project.organization_id)

class ReserveSprintQuotaUseCase:
    def __init__(self, repo: IProjectRepository):
        self.repo = repo

    async def execute(self, project_id: UUID) -> bool:
        return await self.repo.try_reserve_sprint(project_id)
