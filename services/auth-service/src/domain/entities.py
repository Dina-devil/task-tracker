from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

@dataclass
class Role:
    name: str
    permissions: list[str] = field(default_factory=list)

@dataclass
class RefreshToken:
    token_id: str
    user_id: UUID
    expires_at: datetime
    revoked: bool = False

@dataclass
class User:
    id: UUID
    email: str
    hashed_password: str
    role: Role = field(default_factory=lambda: Role(name="MEMBER", permissions=["task:read", "task:write"]))
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
