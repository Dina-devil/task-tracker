from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import redis.asyncio as redis
from src.infrastructure.database import Base, PostgresUserRepository
from src.infrastructure.security import hash_password, verify_password, RedisTokenBlacklist
from src.application.use_cases import RegisterUserUseCase, LoginUserUseCase, LogoutUserUseCase

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@postgres:5432/auth_db")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-jwt-key-change-in-prod")

engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
redis_client = redis.from_url(REDIS_URL, decode_responses=True)
blacklist = RedisTokenBlacklist(redis_client)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await redis_client.aclose()
    await engine.dispose()

app = FastAPI(title="Auth Service", lifespan=lifespan)

class AuthRequest(BaseModel):
    email: EmailStr
    password: str

@app.post("/auth/register", status_code=201)
async def register(req: AuthRequest):
    async with SessionLocal() as session:
        repo = PostgresUserRepository(session)
        uc = RegisterUserUseCase(repo, hash_password)
        try:
            user = await uc.execute(req.email, req.password)
            return {"id": str(user.id), "email": user.email, "role": user.role.name}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

@app.post("/auth/login")
async def login(req: AuthRequest):
    async with SessionLocal() as session:
        repo = PostgresUserRepository(session)
        uc = LoginUserUseCase(repo, verify_password, JWT_SECRET)
        try:
            token = await uc.execute(req.email, req.password)
            return {"access_token": token, "token_type": "bearer"}
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc))

@app.post("/auth/logout")
async def logout(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "").strip()
    uc = LogoutUserUseCase(blacklist)
    await uc.execute(token)
    return {"status": "logged out"}
