from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime, select
from src.domain.entities import User, Role
from src.application.interfaces import IUserRepository

class Base(DeclarativeBase):
    pass

class UserModel(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str]
    role_name: Mapped[str] = mapped_column(default="MEMBER")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class PostgresUserRepository(IUserRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        res = await self.session.execute(select(UserModel).where(UserModel.email == email))
        row = res.scalar_one_or_none()
        if not row:
            return None
        return User(
            id=UUID(row.id),
            email=row.email,
            hashed_password=row.hashed_password,
            role=Role(name=row.role_name),
            is_active=row.is_active,
            created_at=row.created_at,
        )

    async def get_by_id(self, user_id: UUID) -> User | None:
        res = await self.session.execute(select(UserModel).where(UserModel.id == str(user_id)))
        row = res.scalar_one_or_none()
        if not row:
            return None
        return User(
            id=UUID(row.id),
            email=row.email,
            hashed_password=row.hashed_password,
            role=Role(name=row.role_name),
            is_active=row.is_active,
            created_at=row.created_at,
        )

    async def save(self, user: User) -> User:
        created = user.created_at or datetime.now(timezone.utc)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        model = UserModel(
            id=str(user.id),
            email=user.email,
            hashed_password=user.hashed_password,
            role_name=user.role.name,
            is_active=user.is_active,
            created_at=created,
        )
        await self.session.merge(model)
        await self.session.commit()
        return user
