# OSINT Backend

FastAPI + Celery backend for the OSINT Knowledge Graph.

## Structure

```
app/
├── main.py            # FastAPI app factory + lifespan (Neo4j + Postgres schema init)
├── core/
│   ├── config.py      # pydantic-settings configuration
│   └── logging.py     # logging setup
├── schemas/
│   └── article.py     # unified Article model + SourceType (source-agnostic)
├── db/
│   ├── neo4j.py       # driver + schema (constraints/indexes)
│   ├── postgres.py    # connection helper
│   └── articles.py    # articles table: idempotent schema + upsert
├── ingestion/
│   ├── gdelt.py       # GDELT 2.0 GKG fetcher + mapping
│   └── reddit.py      # Reddit (PRAW) hot-thread fetcher + mapping
├── api/routes/
│   └── health.py      # /healthcheck, /readiness
└── workers/
    ├── celery_app.py  # Celery app + Beat schedule (broker: RabbitMQ, backend: Redis)
    └── tasks/
        └── ingest.py  # ingest.gdelt / ingest.reddit tasks
scripts/
└── init_neo4j.py      # standalone schema bootstrap
tests/
├── test_health.py
├── test_article_schema.py
├── test_gdelt.py
└── test_reddit.py
```

## Commands

```bash
pip install -e ".[dev,nlp]"
ruff check .            # lint
ruff format .           # format
pytest                  # tests
uvicorn app.main:app --reload
celery -A app.workers.celery_app worker --loglevel=INFO   # process tasks
celery -A app.workers.celery_app beat --loglevel=INFO     # schedule periodic ingestion
celery -A app.workers.celery_app call ingest.gdelt        # trigger one run manually
python -m scripts.init_neo4j
```
