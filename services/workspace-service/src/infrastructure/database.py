from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import select, update
from src.domain.entities import Project
from src.application.interfaces import IProjectRepository

class Base(DeclarativeBase):
    pass

class OrganizationModel(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    plan: Mapped[str] = mapped_column(default="FREE")

class TeamModel(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(primary_key=True)
    organization_id: Mapped[str]
    name: Mapped[str]

class ProjectModel(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(primary_key=True)
    organization_id: Mapped[str]
    team_id: Mapped[str | None] = mapped_column(nullable=True)
    name: Mapped[str]
    owner_id: Mapped[str]
    active_sprints_count: Mapped[int] = mapped_column(default=0)
    max_active_sprints: Mapped[int] = mapped_column(default=1)

class PostgresProjectRepository(IProjectRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, project_id: UUID) -> Project | None:
        res = await self.session.execute(select(ProjectModel).where(ProjectModel.id == str(project_id)))
        row = res.scalar_one_or_none()
        if not row:
            return None
        return Project(
            id=UUID(row.id),
            organization_id=UUID(row.organization_id),
            team_id=UUID(row.team_id) if row.team_id else None,
            name=row.name,
            owner_id=UUID(row.owner_id),
            active_sprints_count=row.active_sprints_count,
            max_active_sprints=row.max_active_sprints,
        )

    async def save(self, project: Project) -> Project:
        model = ProjectModel(
            id=str(project.id),
            organization_id=str(project.organization_id),
            team_id=str(project.team_id) if project.team_id else None,
            name=project.name,
            owner_id=str(project.owner_id),
            active_sprints_count=project.active_sprints_count,
            max_active_sprints=project.max_active_sprints,
        )
        await self.session.merge(model)
        await self.session.commit()
        return project

    async def try_reserve_sprint(self, project_id: UUID) -> bool:
        stmt = (
            update(ProjectModel)
            .where(
                ProjectModel.id == str(project_id),
                ProjectModel.active_sprints_count < ProjectModel.max_active_sprints,
            )
            .values(active_sprints_count=ProjectModel.active_sprints_count + 1)
            .returning(ProjectModel.id)
        )
        res = await self.session.execute(stmt)
        reserved = res.scalar_one_or_none() is not None
        await self.session.commit()
        return reserved
