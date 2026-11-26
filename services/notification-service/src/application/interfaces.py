from abc import ABC, abstractmethod

class IInboxNotificationStore(ABC):
    @abstractmethod
    async def record_idempotently(self, event_id: str, message: str) -> bool:
        pass
