from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from src.application.use_cases import (CheckProjectAccessUseCase, CreateProjectUseCase, ReserveSprintQuotaUseCase)
from src.domain.entities import Organization, Project, Team


def test_project_sprint_quota_reservation():
    proj = Project(
        id=uuid4(),
        organization_id=uuid4(),
        team_id=None,
        name="Core Platform",
        owner_id=uuid4(),
        active_sprints_count=0,
        max_active_sprints=1,
    )
    assert proj.can_start_sprint() is True
    assert proj.reserve_sprint_slot() is True
    assert proj.active_sprints_count == 1
    assert proj.can_start_sprint() is False
    assert proj.reserve_sprint_slot() is False


def test_organization_and_team_entities():
    org_id = uuid4()
    org = Organization(id=org_id, name="Acme")
    assert org.plan == "FREE"

    member_id = uuid4()
    team = Team(id=uuid4(), organization_id=org_id, name="Backend", member_ids=[member_id])
    assert team.member_ids == [member_id]


@pytest.mark.asyncio
async def test_create_project_use_case():
    repo = AsyncMock()
    repo.save.side_effect = lambda p: p

    uc = CreateProjectUseCase(repo)
    org_id = uuid4()
    owner_id = uuid4()
    team_id = uuid4()

    project = await uc.execute(
        organization_id=org_id,
        name="Mobile App",
        owner_id=owner_id,
        max_active_sprints=3,
        team_id=team_id,
    )

    assert project.organization_id == org_id
    assert project.owner_id == owner_id
    assert project.team_id == team_id
    assert project.name == "Mobile App"
    assert project.active_sprints_count == 0
    assert project.max_active_sprints == 3
    repo.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_project_access_found_and_missing():
    org_id = uuid4()
    project = Project(
        id=uuid4(),
        organization_id=org_id,
        team_id=None,
        name="Platform",
        owner_id=uuid4(),
    )
    repo = AsyncMock()
    repo.get_by_id.side_effect = [project, None]

    uc = CheckProjectAccessUseCase(repo)

    ok, returned_org_id = await uc.execute(project.id, uuid4())
    assert ok is True
    assert returned_org_id == str(org_id)

    ok_missing, missing_org_id = await uc.execute(uuid4(), uuid4())
    assert ok_missing is False
    assert missing_org_id == ""


@pytest.mark.asyncio
async def test_reserve_sprint_quota_use_case():
    repo = AsyncMock()
    repo.try_reserve_sprint.side_effect = [True, False]

    uc = ReserveSprintQuotaUseCase(repo)
    project_id = uuid4()

    assert await uc.execute(project_id) is True
    assert await uc.execute(project_id) is False
    assert repo.try_reserve_sprint.await_count == 2