import json
from uuid import UUID, uuid4
from src.domain.entities import Task, TaskStatus, Sprint, OutboxEvent
from src.application.interfaces import ITaskRepository, ISprintRepository, IWorkspaceClient, ICacheService

class CreateTaskUseCase:
    def __init__(self, task_repo: ITaskRepository, workspace_client: IWorkspaceClient):
        self.task_repo = task_repo
        self.workspace_client = workspace_client

    async def execute(self, project_id: UUID, user_id: str, title: str, description: str) -> Task:
        has_access = await self.workspace_client.verify_access(str(project_id), user_id)
        if not has_access:
            raise PermissionError("User does not have access to this project or project does not exist")

        task = Task(id=uuid4(), project_id=project_id, title=title, description=description, assignee_id=UUID(user_id))
        event = OutboxEvent.create(
            aggregate_type="Task",
            aggregate_id=str(task.id),
            event_type="TaskCreated",
            payload={"task_id": str(task.id), "title": task.title, "project_id": str(project_id)},
        )
        await self.task_repo.save_with_outbox(task, event)
        return task

class UpdateTaskStatusUseCase:
    def __init__(self, task_repo: ITaskRepository, cache: ICacheService):
        self.task_repo = task_repo
        self.cache = cache

    async def execute(self, task_id: UUID, new_status: TaskStatus) -> Task:
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            raise ValueError("Task not found")
        event = task.change_status(new_status)
        await self.task_repo.save_with_outbox(task, event)
        await self.cache.delete(f"task:{task_id}")
        return task

class GetTaskUseCase:
    def __init__(self, task_repo: ITaskRepository, cache: ICacheService):
        self.task_repo = task_repo
        self.cache = cache

    async def execute(self, task_id: UUID) -> dict | None:
        cache_key = f"task:{task_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return json.loads(cached)

        task = await self.task_repo.get_by_id(task_id)
        if not task:
            return None

        data = {
            "id": str(task.id),
            "project_id": str(task.project_id),
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
        }
        await self.cache.set(cache_key, json.dumps(data), ttl=300)
        return data

class StartSprintSagaOrchestrator:
    def __init__(self, sprint_repo: ISprintRepository):
        self.sprint_repo = sprint_repo

    async def start_sprint(self, sprint_id: UUID) -> Sprint:
        sprint = await self.sprint_repo.get_by_id(sprint_id)
        if not sprint:
            raise ValueError("Sprint not found")

        saga_command_event = sprint.initiate_start()
        await self.sprint_repo.save_with_outbox(sprint, saga_command_event)
        return sprint

    async def handle_saga_reply(self, sprint_id: UUID, reply_event: str) -> None:
        sprint = await self.sprint_repo.get_by_id(sprint_id)
        if not sprint:
            return

        if reply_event == "QUOTA_RESERVED":
            started_event = sprint.complete_start()
            await self.sprint_repo.save_with_outbox(sprint, started_event)
        elif reply_event == "QUOTA_EXCEEDED":
            sprint.compensate_start()
            await self.sprint_repo.save_with_outbox(sprint, None)
