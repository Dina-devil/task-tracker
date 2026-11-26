from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

@dataclass
class SubscriptionQuota:
    organization_id: UUID
    plan: str = "FREE"
    max_sprints: int = 1
    max_tasks: int = 100

@dataclass
class Notification:
    id: UUID
    message: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
