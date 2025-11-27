# Telegram Auto-Channels MVP Architecture Proposal

This document outlines a proposed architecture, schema, and implementation plan for a Python 3.11+ application that manages and auto-posts content to multiple Telegram channels.

## Project layout (monorepo, service-style)
```
.
├── app/
│   ├── api/                # FastAPI routers and dependency wiring
│   ├── core/               # Settings, logging, lifecycle utilities
│   ├── db/                 # SQLAlchemy models, session, migrations glue
│   ├── repositories/       # Data access layer (per-aggregate abstractions)
│   ├── services/           # Domain services: scheduler, posting orchestration
│   ├── telegram/           # aiogram bot client & helpers
│   ├── content/            # Content generation strategies and interfaces
│   ├── research/           # (Future) niche research module interfaces
│   └── schemas/            # Pydantic DTOs for API I/O
├── alembic/                # Migration env and versions
├── scripts/                # CLI utilities (manual triggers, backfills)
├── tests/                  # Unit/integration tests
├── docker-compose.yml      # App + Postgres
├── Dockerfile              # Application image
├── README.md
└── pyproject.toml / poetry.lock or requirements.txt
```

### Why aiogram
- Async-first and plays nicely with FastAPI and APScheduler in the same event loop.
- Rich middlewares; mature ecosystem for bots and channel posting.

### Alternative architecture (not chosen)
- Split into multiple services (API, scheduler worker) communicating via a queue. Rejected for MVP simplicity; current layout keeps scheduler in-process but can be split later by extracting shared packages and using a message broker.

## Database schema

### Table: channels
- `id` (UUID primary key)
- `internal_name` (text, unique)
- `telegram_channel_id` (bigint) — channel identifier used by aiogram
- `topic` (text)
- `language_code` (varchar, nullable)
- `posting_frequency_per_day` (smallint) — e.g., 3 posts/day
- `posting_window_start` (time with time zone) — start of allowed window in channel TZ
- `posting_window_end` (time with time zone) — end of allowed window
- `timezone` (varchar) — e.g., "Europe/Berlin"
- `auto_post_enabled` (boolean)
- `content_strategy` (varchar, nullable) — identifier for strategy/LLM prompt style
- `news_source_lists` (jsonb, nullable) — массив списков RSS/Atom лент для новостного дайджеста
- Timestamps: `created_at`, `updated_at`

### Table: posts
- `id` (UUID primary key)
- `channel_id` (FK → channels.id)
- `status` (enum: queued, sent, failed)
- `scheduled_for` (timestamptz) — when scheduler intended to post
- `sent_at` (timestamptz, nullable)
- `error` (text, nullable)
- `content` (text) — generated message
- `created_at`, `updated_at`

### Table: post_metrics (future-ready)
- `id` (UUID)
- `post_id` (FK)
- `views`, `forwards`, `reactions` — nullable ints
- `captured_at` (timestamptz)

### Table: research_jobs (future)
- `id` (UUID)
- `channel_id` (FK, nullable if job is market-wide)
- `job_type` (enum: niche_research, trend_scan, content_brief)
- `status` (enum: queued, running, completed, failed)
- `payload` (jsonb) — parameters
- `result` (jsonb, nullable)
- `started_at`, `completed_at`, `created_at`

## Module responsibilities

### API layer (`app/api`)
- FastAPI routers for channels, post preview, healthcheck.
- Dependency injection for DB session, services, settings.
- Input/output validation via Pydantic schemas.

### DB / repository layer (`app/db`, `app/repositories`)
- SQLAlchemy ORM models and metadata.
- Session management and transaction helpers.
- Repository classes per aggregate (ChannelRepository, PostRepository) abstracting queries, frequency calculations, and history lookups.

### Content generation (`app/content`)
- Interface `ContentGenerator` with `async generate(channel: Channel, now: datetime) -> str`.
- Simple placeholder generator (topic-based template).
- Optional OpenAIChatGenerator implementation using `OPENAI_API_KEY` and channel.strategy to choose prompts.
- Strategy registry allowing channels to choose generator/strategy by name.

### Scheduler (`app/services/scheduler`)
- APScheduler job running periodically (e.g., every 5–10 minutes).
- Steps:
  1. Fetch eligible channels (`auto_post_enabled` = True).
  2. Determine if a channel should post now based on frequency and allowed window (uses helper to compute last sent timestamps from posts table and channel timezone/window).
  3. Generate content via `ContentGenerator` registry.
  4. Send via Telegram client; persist `posts` rows with status.
  5. Handle errors with retries/backoff and logging.
- Exposes hooks to plug in future research jobs or per-channel strategies.

### Telegram integration (`app/telegram`)
- aiogram bot initialization with token from settings.
- Thin wrapper `TelegramClient` with `async send_message(channel_id: int, text: str)` returning message metadata.
- Utilities for parsing channel invite links/usernames if needed.

### Future “niche research” module (`app/research`)
- Interfaces for research jobs and results; scheduling via the same APScheduler or a separate worker.
- Could use external APIs/scrapers; store results in `research_jobs` and related tables.

## Key classes / interfaces

```python
# app/content/interfaces.py
class ContentGenerator(Protocol):
    async def generate(self, channel: Channel, now: datetime) -> str: ...

# app/content/registry.py
class ContentRegistry:
    def register(self, name: str, generator: ContentGenerator): ...
    def get(self, name: str) -> ContentGenerator: ...

# app/services/scheduler/service.py
class SchedulerService:
    async def run_tick(self, now: datetime): ...  # used by APScheduler job

# app/services/posting.py
class PostingService:
    async def should_post(self, channel: Channel, now: datetime) -> bool: ...
    async def create_and_send_post(self, channel: Channel, now: datetime) -> Post: ...

# app/telegram/client.py
class TelegramClient:
    async def send_message(self, channel_id: int, text: str) -> TelegramMessage: ...

# app/repositories/channels.py
class ChannelRepository:
    async def list(self) -> list[Channel]: ...
    async def get(self, channel_id: UUID) -> Channel: ...
    async def upsert(self, data: ChannelCreate) -> Channel: ...

# app/repositories/posts.py
class PostRepository:
    async def record_post(self, channel_id: UUID, content: str, status: PostStatus, scheduled_for: datetime, error: str | None = None): ...
    async def last_posts(self, channel_id: UUID, limit: int = 10): ...

# FastAPI routers use schemas in app/schemas/
```

## Implementation plan (8–12 steps)
1. **Project scaffolding**: Initialize `pyproject.toml`/requirements, `.env.example`, Dockerfile, docker-compose with Postgres.
2. **Settings & logging**: Add Pydantic settings, logging config, dependency injection helpers, `main.py` to create FastAPI app and lifespan hooks.
3. **Database layer**: Configure SQLAlchemy engine/session, create base models and enums; set up Alembic env.
4. **Models & migrations**: Define `channels`, `posts` tables; generate and stamp initial migration.
5. **Repositories**: Implement ChannelRepository and PostRepository with basic CRUD and helper queries for scheduling decisions.
6. **Content module**: Add interfaces, registry, placeholder generator, optional OpenAI-based generator controlled by settings/feature flag.
7. **Telegram client**: Configure aiogram bot and wrapper for sending messages; include mockable interface for tests.
8. **Posting/Scheduler services**: Implement scheduling logic (frequency/window checks), posting workflow, error handling; wire APScheduler startup/shutdown.
9. **API layer**: Implement routers for healthcheck, list/create/update channels, and preview endpoint that calls content generator without sending.
10. **Scripts & dev tooling**: Add scripts for seeding channels, manual post trigger; basic tests for content generator and scheduling logic.
11. **Observability**: Add structured logging and minimal metrics hooks (placeholder); ensure error paths log context.
12. **Docs**: Update README with setup/run instructions and architectural overview.

## Extensibility notes
- Content strategies are decoupled via registry; new strategies can be registered without touching scheduler.
- Scheduler uses services/repositories so posting rules can evolve (e.g., A/B tests, rate limits) without API changes.
- Research module can reuse scheduler infrastructure and store results in dedicated tables; API can expose research jobs later without breaking current interfaces.
```
