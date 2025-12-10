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

Channel payloads support the following fields:

- `content_strategy` — `placeholder` (default), `openai`, or `news`.
- `news_source_lists` — массив списков RSS/Atom-источников, из которых собираются свежие новости для стратегии `news`.

### News digest quickstart
1. Убедитесь, что задали `OPENAI_API_KEY` в `.env` — без него стратегия `news` не будет активирована.
2. Создайте канал через API с `content_strategy: "news"` и подключёнными RSS/Atom источниками (можно группировать по тематикам):
   ```json
   {
     "internal_name": "it-daily",
     "telegram_channel_id": 123456789,
     "topic": "IT новости",
     "content_strategy": "news",
     "news_source_lists": [
       [
         "https://habr.com/ru/rss/all/all/",
         "https://www.theverge.com/rss/index.xml"
       ]
     ],
     "auto_post_enabled": true
   }
   ```
3. Планировщик возьмёт самые свежие материалы за последние 24 часа из указанных лент, выберет наиболее недавний, переведёт и суммирует его на русском.
4. В канал улетит короткий дайджест из 2–3 предложений со ссылкой на оригинал. Пример сообщения:
   ```
   Apple представила новые MacBook Pro на чипе M4, обещая заметный рост производительности и автономности. Обновлены дисплеи, улучшено охлаждение и добавлены новые порты для профессионалов.

   Источник: https://www.theverge.com/example-article
   ```

## Development
- Content strategies are registered in `app/content/factory.py`.
- Scheduler behavior lives in `app/services/scheduler.py` and `app/services/posting.py`.
