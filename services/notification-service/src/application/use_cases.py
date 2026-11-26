from src.application.interfaces import IInboxNotificationStore

class ProcessDomainEventInboxUseCase:
    def __init__(self, store: IInboxNotificationStore):
        self.store = store

    async def execute(self, event_id: str, payload_json: str) -> bool:
        return await self.store.record_idempotently(event_id, f"Event processed: {payload_json}")
