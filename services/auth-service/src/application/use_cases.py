from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import jwt
from src.domain.entities import User, Role
from src.application.interfaces import IUserRepository, ITokenBlacklist

class RegisterUserUseCase:
    def __init__(self, user_repo: IUserRepository, hash_fn):
        self.user_repo = user_repo
        self.hash_fn = hash_fn

    async def execute(self, email: str, password: str, role_name: str = "MEMBER") -> User:
        existing = await self.user_repo.get_by_email(email)
        if existing:
            raise ValueError("Email already registered")
        user = User(
            id=uuid4(),
            email=email,
            hashed_password=self.hash_fn(password),
            role=Role(name=role_name, permissions=["task:read", "task:write"]),
        )
        return await self.user_repo.save(user)

class LoginUserUseCase:
    def __init__(self, user_repo: IUserRepository, verify_fn, secret: str, algorithm: str = "HS256"):
        self.user_repo = user_repo
        self.verify_fn = verify_fn
        self.secret = secret
        self.algorithm = algorithm

    async def execute(self, email: str, password: str) -> str:
        user = await self.user_repo.get_by_email(email)
        if not user or not user.is_active or not self.verify_fn(password, user.hashed_password):
            raise PermissionError("Invalid credentials")
        expire = datetime.now(timezone.utc) + timedelta(hours=2)
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.name,
            "exp": expire,
        }
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

class LogoutUserUseCase:
    def __init__(self, blacklist: ITokenBlacklist):
        self.blacklist = blacklist

    async def execute(self, token: str, ttl_seconds: int = 7200) -> None:
        await self.blacklist.add(token, ttl_seconds)
