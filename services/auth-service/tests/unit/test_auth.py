from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4
import jwt
import pytest
from src.application.use_cases import (LoginUserUseCase, LogoutUserUseCase, RegisterUserUseCase)
from src.domain.entities import Role, User
from src.infrastructure.security import (RedisTokenBlacklist, hash_password, verify_password)


def test_password_hashing_and_verification():
    hashed = hash_password("StrongPass123!")
    assert hashed != "StrongPass123!"
    assert verify_password("StrongPass123!", hashed) is True
    assert verify_password("WrongPass", hashed) is False


@pytest.mark.asyncio
async def test_register_user_success_and_duplicate():
    repo = AsyncMock()
    existing_user = User(
        id=uuid4(),
        email="taken@example.com",
        hashed_password=hash_password("Pass123!"),
    )
    repo.get_by_email.side_effect = [None, existing_user]
    repo.save.side_effect = lambda u: u

    uc = RegisterUserUseCase(repo, hash_password)
    user = await uc.execute("new@example.com", "SecretPass123!", role_name="MEMBER")

    assert user.email == "new@example.com"
    assert verify_password("SecretPass123!", user.hashed_password) is True
    assert user.role.name == "MEMBER"
    assert "task:read" in user.role.permissions
    repo.save.assert_awaited_once()

    with pytest.raises(ValueError, match="Email already registered"):
        await uc.execute("taken@example.com", "SecretPass123!")


@pytest.mark.asyncio
async def test_login_user_jwt_and_invalid_cases():
    secret = "test-jwt-secret"
    user_id = uuid4()
    active_user = User(
        id=user_id,
        email="member@example.com",
        hashed_password=hash_password("MyPass123!"),
        role=Role(name="ADMIN", permissions=["task:read", "task:write"]),
        is_active=True,
    )
    inactive_user = User(
        id=uuid4(),
        email="blocked@example.com",
        hashed_password=hash_password("MyPass123!"),
        is_active=False,
    )

    repo = AsyncMock()
    repo.get_by_email.side_effect = [
        active_user,
        active_user,
        None,
        inactive_user,
    ]

    uc = LoginUserUseCase(repo, verify_password, secret=secret, algorithm="HS256")

    token = await uc.execute("member@example.com", "MyPass123!")
    decoded = jwt.decode(token, secret, algorithms=["HS256"])
    assert decoded["sub"] == str(user_id)
    assert decoded["email"] == "member@example.com"
    assert decoded["role"] == "ADMIN"
    assert datetime.fromtimestamp(decoded["exp"], tz=timezone.utc) > datetime.now(timezone.utc)

    with pytest.raises(PermissionError, match="Invalid credentials"):
        await uc.execute("member@example.com", "WrongPassword!")

    with pytest.raises(PermissionError, match="Invalid credentials"):
        await uc.execute("nobody@example.com", "MyPass123!")

    with pytest.raises(PermissionError, match="Invalid credentials"):
        await uc.execute("blocked@example.com", "MyPass123!")


@pytest.mark.asyncio
async def test_logout_and_redis_blacklist_contains():
    redis_mock = AsyncMock()
    redis_mock.exists.side_effect = [1, 0]

    bl = RedisTokenBlacklist(redis_mock)
    uc = LogoutUserUseCase(bl)

    await uc.execute("sample.jwt.token", ttl_seconds=3600)
    redis_mock.setex.assert_awaited_once_with("blacklist:sample.jwt.token", 3600, "revoked")

    assert await bl.contains("sample.jwt.token") is True
    assert await bl.contains("other.jwt.token") is False
    redis_mock.exists.assert_any_await("blacklist:sample.jwt.token")
    redis_mock.exists.assert_any_await("blacklist:other.jwt.token")
