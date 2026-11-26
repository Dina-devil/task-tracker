from passlib.context import CryptContext
import redis.asyncio as redis
from src.application.interfaces import ITokenBlacklist

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

class RedisTokenBlacklist(ITokenBlacklist):
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def add(self, token: str, ttl_seconds: int = 7200) -> None:
        await self.redis.setex(f"blacklist:{token}", ttl_seconds, "revoked")

    async def contains(self, token: str) -> bool:
        return await self.redis.exists(f"blacklist:{token}") > 0
