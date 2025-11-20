# tg-auto-channels

Telegram autoposting MVP using FastAPI, aiogram, SQLAlchemy, and APScheduler.

## Requirements
- Python 3.11+
- Docker & docker-compose

## Configuration
Create a `.env` file (see `.env.example`). Key variables:
- `DATABASE_URL` (asyncpg URL)
- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY` (optional)
- `POSTING_INTERVAL_MINUTES` scheduler tick interval

## Running locally
1. Install dependencies: `pip install -e .[dev]`.
2. Run migrations: `alembic upgrade head`.
3. Start the API: `uvicorn app.main:app --reload`.
4. Scheduler runs inside the FastAPI lifespan.

## Docker
- `docker-compose up --build`
- API available on `http://localhost:8000` by default.

## API
- `GET /health` — healthcheck.
- `GET /channels/` — list channels.
- `POST /channels/` — create or upsert a channel.
- `PUT /channels/{id}` — update channel.
- `GET /preview/{id}` — generate a post without sending.

## Development
- Content strategies are registered in `app/content/factory.py`.
- Scheduler behavior lives in `app/services/scheduler.py` and `app/services/posting.py`.
