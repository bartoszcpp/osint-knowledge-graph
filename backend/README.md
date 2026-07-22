# OSINT Backend

FastAPI + Celery backend for the OSINT Knowledge Graph.

## Structure

```
app/
├── main.py            # FastAPI app factory + lifespan (Neo4j + Postgres schema init)
├── core/
│   ├── config.py      # pydantic-settings configuration
│   ├── logging.py     # logging setup
│   └── cache.py       # best-effort Redis JSON cache for graph reads (Phase 5)
├── schemas/
│   ├── article.py     # unified Article model + SourceType (source-agnostic)
│   ├── analysis.py    # EntityType, EntityMention, ResolvedEntity, Relation
│   ├── graph.py       # GraphBatch payload (UNWIND rows for Neo4j)
│   └── api.py         # API response models (entities, ego-graph, articles)
├── db/
│   ├── neo4j.py       # driver + schema (Entity/Article constraints & indexes)
│   ├── postgres.py    # connection helper
│   ├── articles.py    # articles table + upsert + processed/graphed tracking
│   └── analysis.py    # article_entities / article_relations tables + save/fetch
├── ingestion/
│   ├── gdelt.py       # GDELT 2.0 GKG fetcher + mapping
│   └── reddit.py      # Reddit (PRAW) hot-thread fetcher + mapping
├── nlp/
│   ├── pipeline.py    # spaCy model load + PERSON/ORG/GPE mention extraction
│   ├── resolution.py  # in-article entity resolution (dedup)
│   ├── relations.py   # co-occurrence relation detection
│   └── processor.py   # orchestrator: Article -> ArticleAnalysis
├── graph/
│   ├── writer.py      # batched UNWIND payload builder + Neo4j writes
│   └── reader.py      # graph read queries (top entities, ego-graph, articles)
├── api/routes/
│   ├── health.py      # /healthcheck, /readiness
│   └── graph.py       # /entities, /graph/{id}, /articles (paginated + cached)
└── workers/
    ├── celery_app.py  # Celery app + Beat + nlp_tasks queue routing
    └── tasks/
        ├── ingest.py  # ingest.gdelt / ingest.reddit
        ├── nlp.py     # nlp.dispatch_pending / nlp.process_article
        └── graph.py   # graph.sync_pending (batched Neo4j write)
scripts/
└── init_neo4j.py      # standalone schema bootstrap
tests/
├── test_health.py
├── test_article_schema.py
├── test_gdelt.py
├── test_reddit.py
├── test_nlp_resolution.py
├── test_nlp_relations.py
├── test_nlp_processor.py
├── test_nlp_pipeline.py   # spaCy integration (auto-skips without the model)
├── test_graph_writer.py   # batched payload builder
└── test_api_graph.py      # Phase 5 API (reader + cache mocked)
```

## Commands

```bash
pip install -e ".[dev]"
python -m spacy download en_core_web_sm   # NER model (Phase 3)
ruff check .            # lint
ruff format .           # format
pytest                  # tests
uvicorn app.main:app --reload
celery -A app.workers.celery_app worker -Q celery --loglevel=INFO      # ingestion + dispatch
celery -A app.workers.celery_app worker -Q nlp_tasks --loglevel=INFO   # CPU-heavy NER
celery -A app.workers.celery_app beat --loglevel=INFO                  # periodic scheduler
celery -A app.workers.celery_app call ingest.gdelt                     # trigger ingestion
celery -A app.workers.celery_app call nlp.dispatch_pending             # trigger NLP
celery -A app.workers.celery_app call graph.sync_pending               # flush to Neo4j
python -m scripts.init_neo4j
```
