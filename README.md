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

> **Status: Phase 4 — Knowledge Graph (Neo4j).**
> Analyzed entities and relations are flushed into Neo4j in batches: `Entity` and
> `Article` nodes, `(:Entity)-[:MENTIONED_IN]->(:Article)` edges, and undirected
> `(:Entity)-[:CO_OCCURS_WITH {weight}]-(:Entity)` edges whose weight grows each
> time two entities meet in another article. The query API and graph UI land next.

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
| worker     | Celery worker (ingestion + dispatch)   | —                 |
| nlp-worker | Celery worker (CPU-heavy NER)          | —                 |
| beat       | Celery Beat (periodic cron scheduler)  | —                 |

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

## NLP & entity extraction (Phase 3)

Stored articles are turned into structured entities and relations by a dedicated
CPU-heavy Celery queue (`nlp_tasks`, served by the `nlp-worker`).

- **Dispatch:** `nlp.dispatch_pending` (Beat, every `NLP_DISPATCH_INTERVAL_MINUTES`,
  also fired right after ingestion) scans Postgres for unprocessed articles and
  fans out one `nlp.process_article` task each, routed to the `nlp_tasks` queue.
- **NER:** spaCy (`SPACY_MODEL`, default `en_core_web_sm`; swap for the
  transformer `en_core_web_trf` via the `nlp` extra) extracts `PERSON`, `ORG` and
  `GPE` entities.
- **Entity resolution:** a rule-based resolver de-duplicates mentions *within an
  article* — e.g. "Elon Musk", "Musk" and "E. Musk" collapse to one node.
- **Relations:** entities co-occurring in the same sentence (or paragraph, via
  `NLP_COOCCURRENCE_SCOPE`) become weighted undirected edges.
- **Storage:** results land in `article_entities` / `article_relations`; the
  source article is stamped `processed_at`.

```bash
# process everything pending now, without waiting for the scheduler
celery -A app.workers.celery_app call nlp.dispatch_pending

# inspect results
docker compose exec postgres psql -U osint -d osint -c \
  "select type, name, mention_count from article_entities order by mention_count desc limit 10;"
docker compose exec postgres psql -U osint -d osint -c \
  "select source_name, target_name, weight from article_relations order by weight desc limit 10;"
```

## Knowledge graph (Phase 4)

Analyzed articles are flushed into Neo4j by `graph.sync_pending` (Beat, every
`GRAPH_SYNC_INTERVAL_MINUTES`), which pulls a batch of articles that are
NER-processed but not yet graphed and writes them with a few `UNWIND`-driven
Cypher statements — one round-trip per node/edge type instead of thousands of
small queries.

- **Nodes:** `(:Entity {canonical_id, name, type})` and
  `(:Article {url, article_id, title, published_at, source})`.
- **Mentions:** `(:Entity)-[:MENTIONED_IN {count}]->(:Article)`.
- **Co-occurrence:** undirected `(:Entity)-[:CO_OCCURS_WITH {weight}]-(:Entity)`;
  `weight` is incremented every time the pair co-occurs in another article.
- **Idempotent & batched:** every write `MERGE`s on the unique key; the batch size
  is `GRAPH_SYNC_BATCH_SIZE` (default 100 articles).

```bash
# flush pending articles to Neo4j now
celery -A app.workers.celery_app call graph.sync_pending
```

Explore in the Neo4j Browser (http://localhost:7474):

```cypher
// strongest connections in the graph
MATCH (a:Entity)-[r:CO_OCCURS_WITH]-(b:Entity)
RETURN a.name, b.name, r.weight ORDER BY r.weight DESC LIMIT 25;

// everything mentioned in a given article
MATCH (e:Entity)-[:MENTIONED_IN]->(a:Article)
RETURN a.title, collect(e.name) LIMIT 10;
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
- **Phase 2 — Ingestion pipeline (done):** Celery + Beat, GDELT 2.0 & Reddit
  fetchers, unified `Article` model, raw storage in PostgreSQL.
- **Phase 3 — NLP & entity extraction (done):** dedicated `nlp_tasks` queue,
  spaCy NER (PERSON/ORG/GPE), in-article entity resolution, co-occurrence
  relations stored in PostgreSQL.
- **Phase 4 — Knowledge graph (this):** batched `UNWIND` writes of entities and
  relations into Neo4j (`Entity`/`Article` nodes, `MENTIONED_IN` +
  `CO_OCCURS_WITH` edges with cumulative weights).
- **Phase 5 — Graph API & UI:** query endpoints, React Flow / 3D graph,
  clustering, virtualization, live search.
