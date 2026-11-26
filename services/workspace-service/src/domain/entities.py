from dataclasses import dataclass, field
from uuid import UUID

@dataclass
class Organization:
    id: UUID
    name: str
    plan: str = "FREE"

@dataclass
class Team:
    id: UUID
    organization_id: UUID
    name: str
    member_ids: list[UUID] = field(default_factory=list)

@dataclass
class Project:
    id: UUID
    organization_id: UUID
    team_id: UUID | None
    name: str
    owner_id: UUID
    active_sprints_count: int = 0
    max_active_sprints: int = 1

    def can_start_sprint(self) -> bool:
        return self.active_sprints_count < self.max_active_sprints

    def reserve_sprint_slot(self) -> bool:
        if not self.can_start_sprint():
            return False
        self.active_sprints_count += 1
        return True
