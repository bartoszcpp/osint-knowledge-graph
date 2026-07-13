# OSINT Backend

FastAPI + Celery backend for the OSINT Knowledge Graph.

## Structure

```
app/
├── main.py            # FastAPI app factory + lifespan (Neo4j schema init)
├── core/
│   ├── config.py      # pydantic-settings configuration
│   └── logging.py     # logging setup
├── db/
│   ├── neo4j.py       # driver + schema (constraints/indexes)
│   └── postgres.py    # connection helper
├── api/routes/
│   └── health.py      # /healthcheck, /readiness
└── workers/
    └── celery_app.py  # Celery app (broker: RabbitMQ, backend: Redis)
scripts/
└── init_neo4j.py      # standalone schema bootstrap
tests/
└── test_health.py
```

## Commands

```bash
pip install -e ".[dev,nlp]"
ruff check .            # lint
ruff format .           # format
pytest                  # tests
uvicorn app.main:app --reload
celery -A app.workers.celery_app worker --loglevel=INFO
python -m scripts.init_neo4j
```
