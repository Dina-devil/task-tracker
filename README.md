# Таск-трекер
## Ограниченные контексты и агрегаты (12 агрегатов)

* **Вход и доступ (`auth-service`)** — `User`, `Role`, `RefreshToken`: аккаунты, роли и выход из системы с блокировкой токена.
* **Компании и проекты (`workspace-service`)** — `Organization`, `Team`, `Project`: организации, команды, проекты и проверка прав у участника перед созданием задачи.
* **Задачи и спринты (`task-service`)** — `Task`, `Sprint`, `Board`, `Comment`: задачи и их статусы, спринты с проверкой лимитов при запуске, доски и комментарии.
* **Уведомления (`notification-service`)** — `Notification`, `SubscriptionQuota`: отправка уведомлений без повторов.

## Схема архитектуры

```text
                ┌──────────────────┐
                │   auth-service   │
                │  User, Role,     │
                │  RefreshToken    │
                └────────┬─────────┘
                         │ blacklist:{token} (Redis)
                         ▼
┌──────────────────┐   gRPC    ┌──────────────────┐
│workspace-service ├──────────►│   task-service   │
│Organization, Team│  access & │Task, Sprint,     │
│Project           │  quota    │Board, Comment    │
└────────┬─────────┘           └──┬────────┬──────┘
         │                        │        │
         │   RabbitMQ (topics &   │        │ PostgreSQL
         │   saga queues)         │        │ (save_with_outbox:
         ▼                        ▼        │  entities + outbox_messages)
┌──────────────────┐  run_outbox_relay   │
│notification-     │◄─────────┴────────┘
│service           │
│Notification,     │
│SubscriptionQuota │
│(inbox_messages)  │
└──────────────────┘

```

## Ключевые паттерны и интеграции

- **PostgreSQL + SQLAlchemy Async** — у каждого сервиса своя база (`infra/init-db.sql`), работа с ними идёт через асинхронные репозитории (`PostgresTaskRepository`, `PostgresSprintRepository`).
- **Redis** — хранит кеш задач (`task:{id}`) и список отозванных токенов (`blacklist:{token}`).
- **gRPC** (`proto/workspace.proto`) — перед созданием задачи сервис задач спрашивает сервис рабочих пространств, есть ли у пользователя доступ к проекту (`CheckProjectAccess`).
- **Transactional Outbox + RabbitMQ** — сущность и событие сохраняются в БД в одной транзакции (`outbox_messages`), а фоновый процесс (`run_outbox_relay`) отправляет их в RabbitMQ и отмечает как обработанные.
- **Saga Orchestration** — при старте спринта статус сначала становится `PENDING_START` и отправляется запрос на проверку квоты; если всё ок — спринт запускается (`ACTIVE`), если нет — возвращается назад (`PLANNED`).
- **Transactional Inbox** — сервис уведомлений записывает пришедшие события по ID (`inbox_messages`), чтобы не обрабатывать одно и то же дважды.


## Локальные адреса (localhost)

* **Task Service (Swagger / API)**: http://localhost:8003/docs
* **Notification Service (Swagger / API)**: http://localhost:8004/docs
* **RabbitMQ Management UI**: http://localhost:15672

## Запуск

```bash
docker compose up -d --build

```