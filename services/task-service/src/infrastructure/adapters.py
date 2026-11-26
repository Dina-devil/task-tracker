import grpc
import redis.asyncio as redis
import workspace_pb2
import workspace_pb2_grpc
from src.application.interfaces import IWorkspaceClient, ICacheService

class GrpcWorkspaceClient(IWorkspaceClient):
    def __init__(self, target: str):
        self.target = target

    async def verify_access(self, project_id: str, user_id: str) -> bool:
        async with grpc.aio.insecure_channel(self.target) as channel:
            stub = workspace_pb2_grpc.WorkspaceServiceStub(channel)
            response = await stub.CheckProjectAccess(
                workspace_pb2.ProjectAccessRequest(project_id=project_id, user_id=user_id)
            )
            return response.has_access

class RedisCacheService(ICacheService):
    def __init__(self, redis_url: str, auth_redis_url: str | None = None):
        self.client = redis.from_url(redis_url, decode_responses=True)
        self.auth_client = redis.from_url(auth_redis_url, decode_responses=True) if auth_redis_url else self.client

    async def get(self, key: str) -> str | None:
        return await self.client.get(key)

    async def set(self, key: str, value: str, ttl: int = 300) -> None:
        await self.client.setex(key, ttl, value)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def is_token_blacklisted(self, token: str) -> bool:
        return await self.auth_client.exists(f"blacklist:{token}") > 0

    async def close(self) -> None:
        await self.client.aclose()
        if self.auth_client is not self.client:
            await self.auth_client.aclose()
