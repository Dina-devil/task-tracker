import os
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.domain.entities import Role, User
from src.infrastructure.database import Base, PostgresUserRepository
from src.presentation.api import JWT_SECRET, app

TEST_DB_URL = os.getenv(
    "TEST_AUTH_DB_URL",
    os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/auth_db",
    ),
)


@pytest.mark.asyncio
async def test_postgres_user_repository_crud():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid4()
    email = f"user_{uuid4().hex[:8]}@example.com"
    user = User(
        id=user_id,
        email=email,
        hashed_password="hashed_value",
        role=Role(name="ADMIN", permissions=["task:read", "task:write"]),
    )

    async with Session() as session:
        repo = PostgresUserRepository(session)
        await repo.save(user)

    async with Session() as session:
        repo = PostgresUserRepository(session)
        by_email = await repo.get_by_email(email)
        assert by_email is not None
        assert by_email.id == user_id
        assert by_email.role.name == "ADMIN"

        by_id = await repo.get_by_id(user_id)
        assert by_id is not None
        assert by_id.email == email

        by_email.is_active = False
        await repo.save(by_email)

    async with Session() as session:
        repo = PostgresUserRepository(session)
        updated = await repo.get_by_id(user_id)
        assert updated is not None
        assert updated.is_active is False

        assert await repo.get_by_id(uuid4()) is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_auth_http_register_login_and_logout():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    blacklist_mock = AsyncMock()
    blacklist_mock.add = AsyncMock(return_value=None)

    email = f"api_{uuid4().hex[:8]}@example.com"
    password = "ApiPassword123!"

    with (
        patch("src.presentation.api.SessionLocal", TestSessionLocal),
        patch("src.presentation.api.blacklist", blacklist_mock),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg_res = await client.post(
                "/auth/register",
                json={"email": email, "password": password},
            )
            assert reg_res.status_code == 201
            reg_body = reg_res.json()
            assert reg_body["email"] == email
            assert reg_body["role"] == "MEMBER"

            dup_res = await client.post(
                "/auth/register",
                json={"email": email, "password": password},
            )
            assert dup_res.status_code == 400
            assert "already registered" in dup_res.json()["detail"].lower()

            bad_login = await client.post(
                "/auth/login",
                json={"email": email, "password": "WrongPassword!"},
            )
            assert bad_login.status_code == 401

            login_res = await client.post(
                "/auth/login",
                json={"email": email, "password": password},
            )
            assert login_res.status_code == 200
            login_body = login_res.json()
            assert login_body["token_type"] == "bearer"
            token = login_body["access_token"]
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            assert payload["email"] == email

            logout_res = await client.post(
                "/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert logout_res.status_code == 200
            assert logout_res.json() == {"status": "logged out"}
            blacklist_mock.add.assert_awaited_once_with(token, 7200)

    await engine.dispose()
