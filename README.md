# OSINT Knowledge Graph & Entity Tracker

Platform that analyzes worldwide news streams to discover relationships between
**people, organizations, and events**, and builds an interactive **Knowledge
Graph** out of them.

- **Data sources:** [GDELT](https://www.gdeltproject.org/) (refreshed every 15 min),
  HackerNews API, Reddit API.
- **Backend:** Python — FastAPI, spaCy/Transformers (NER), Neo4j + PostgreSQL,
  Celery workers over RabbitMQ.
- **Frontend:** React + React Flow / 3D Force-Directed Graph, with clustering and
  client-side virtualization for smooth exploration of thousands of nodes.

> **Status: Phase 2 — Ingestion Pipeline.**
> Celery Beat schedules periodic fetchers (GDELT 2.0 + Reddit) that map every
> source onto a unified `Article` model and store raw rows in PostgreSQL.
> The NER pipeline and graph UI land in later phases.

## Repository layout (monorepo)

```
.
├── backend/     # FastAPI app, Celery workers, DB access, tests
├── frontend/    # React + Vite client (graph UI)
├── infra/       # Infra assets (Neo4j schema bootstrap, etc.)
├── docker-compose.yml
├── .env.example
└── .pre-commit-config.yaml
```

## Services (docker-compose)

| Service    | Purpose                                | Ports (host)      |
| ---------- | -------------------------------------- | ----------------- |
| postgres   | Raw articles, logs, provenance         | 5432              |
| neo4j      | Knowledge graph (with APOC plugin)     | 7474, 7687        |
| redis      | Cache + Celery result backend          | 6379              |
| rabbitmq   | Celery broker + management UI          | 5672, 15672       |
| api        | FastAPI application                    | 8000              |
| worker     | Celery worker (NLP / ingestion)        | —                 |
| beat       | Celery Beat (periodic ingestion cron)  | —                 |

## Quickstart

```bash
# 1. Configure environment
cp .env.example .env      # then edit secrets

# 2. Bring up the stack
docker compose up -d --build

# 3. Verify
curl http://localhost:8000/healthcheck
#  -> {"status":"ok","version":"0.1.0","environment":"development"}

curl http://localhost:8000/readiness   # deep check (neo4j + postgres)
```

- FastAPI docs: http://localhost:8000/docs
- Neo4j Browser: http://localhost:7474
- RabbitMQ UI: http://localhost:15672

## Neo4j schema

Constraints (unique business keys, backed by indexes → O(1) lookups) and
secondary indexes are created automatically on API startup. To (re)apply
manually:

```bash
# from inside the api/worker container
python -m scripts.init_neo4j
# or with cypher-shell
cat infra/neo4j/init/01_schema.cypher | cypher-shell -u neo4j -p <password>
```

## Ingestion pipeline (Phase 2)

A distributed Celery pipeline periodically pulls fresh data, normalizes it, and
stores the raw result in PostgreSQL as a durable backup for rebuilding the graph.

- **Scheduler:** Celery Beat fires `ingest.gdelt` and `ingest.reddit` every 15 min
  (configurable via `INGEST_*_INTERVAL_MINUTES`).
- **GDELT 2.0:** reads `lastupdate.txt`, downloads the newest 15-minute **GKG**
  file, and maps each document (URL, timestamp, extracted people/orgs/tone) to an
  `Article`.
- **Reddit:** pulls "hot" threads from `r/worldnews` and `r/business` via PRAW
  (needs `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` and `REDDIT_ENABLED=true`).
- **Unified model:** every source maps to `app/schemas/article.py::Article`
  (`id, source, url, title, text_content, published_at` + provenance).
- **Storage:** `articles` table in PostgreSQL, de-duplicated on a deterministic
  `id` (`ON CONFLICT DO NOTHING`). Schema is created idempotently on startup.

Trigger a run manually (e.g. to test without waiting for the cron):

```bash
# from inside the worker container
celery -A app.workers.celery_app call ingest.gdelt
celery -A app.workers.celery_app call ingest.reddit
```

## Local development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,nlp]"
ruff check . && ruff format --check .
pytest
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run lint
npm run dev
```

### Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

## Roadmap

- **Phase 1 — Foundations & infra (done):** monorepo, linters, pre-commit,
  docker-compose, FastAPI `/healthcheck`, Neo4j schema & indexes.
- **Phase 2 — Ingestion pipeline (this):** Celery + Beat, GDELT 2.0 & Reddit
  fetchers, unified `Article` model, raw storage in PostgreSQL.
- **Phase 3 — NER & graph:** spaCy/Transformers NER over stored articles, write
  entities & relations to Neo4j.
- **Phase 4 — Graph API & UI:** query endpoints, React Flow / 3D graph,
  clustering, virtualization, live search.
