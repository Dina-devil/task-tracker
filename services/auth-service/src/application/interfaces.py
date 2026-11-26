from abc import ABC, abstractmethod
from uuid import UUID
from src.domain.entities import User

class IUserRepository(ABC):
    @abstractmethod
    async def get_by_email(self, email: str) -> User | None:
        pass

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> User | None:
        pass

    @abstractmethod
    async def save(self, user: User) -> User:
        pass

class ITokenBlacklist(ABC):
    @abstractmethod
    async def add(self, token: str, ttl_seconds: int) -> None:
        pass

    @abstractmethod
    async def contains(self, token: str) -> bool:
        pass
