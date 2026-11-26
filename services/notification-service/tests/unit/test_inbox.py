from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.use_cases import ProcessDomainEventInboxUseCase
from src.domain.entities import Notification, SubscriptionQuota


@pytest.mark.asyncio
async def test_inbox_deduplication_and_message_format():
    store = AsyncMock()
    store.record_idempotently.side_effect = [True, False, True]
    uc = ProcessDomainEventInboxUseCase(store)

    payload_a = '{"task_id":"1","status":"IN_PROGRESS"}'
    first = await uc.execute("evt-123", payload_a)
    second = await uc.execute("evt-123", payload_a)
    third = await uc.execute("evt-124", payload_a)

    assert first is True
    assert second is False
    assert third is True

    store.record_idempotently.assert_any_await("evt-123", f"Event processed: {payload_a}")
    store.record_idempotently.assert_any_await("evt-124", f"Event processed: {payload_a}")


def test_domain_entities_defaults():
    org_id = uuid4()
    quota = SubscriptionQuota(organization_id=org_id)
    assert quota.organization_id == org_id
    assert quota.plan == "FREE"
    assert quota.max_sprints == 1
    assert quota.max_tasks == 100

    notif = Notification(id=uuid4(), message="Event processed: {}")
    assert notif.created_at is not None