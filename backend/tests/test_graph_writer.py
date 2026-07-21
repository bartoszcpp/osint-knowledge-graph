"""Tests for the batched graph payload builder (pure, no Neo4j)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.graph.writer import build_batch
from app.schemas.analysis import ArticleAnalysis, EntityType, Relation, ResolvedEntity
from app.schemas.article import Article, SourceType


def _article(article_id: str, url: str) -> Article:
    return Article.model_construct(
        id=article_id,
        source=SourceType.GDELT,
        url=url,
        title="t",
        text_content=None,
        published_at=datetime(2026, 7, 21, tzinfo=UTC),
        raw={},
    )


def _entity(cid: str, name: str, etype: EntityType, count: int) -> ResolvedEntity:
    return ResolvedEntity(canonical_id=cid, name=name, type=etype, mention_count=count)


def _relation(a: str, b: str) -> Relation:
    return Relation(
        source_id=a,
        target_id=b,
        source_name=a,
        target_name=b,
        source_type=EntityType.PERSON,
        target_type=EntityType.ORG,
        weight=1,
    )


def test_build_batch_dedupes_entities_and_accumulates_weight():
    articles = [_article("a1", "https://x.com/a"), _article("a2", "https://x.com/b")]
    analyses = [
        ArticleAnalysis(
            article_id="a1",
            entities=[
                _entity("person:elon-musk", "Musk", EntityType.PERSON, 2),
                _entity("org:tesla", "Tesla", EntityType.ORG, 1),
            ],
            relations=[_relation("org:tesla", "person:elon-musk")],
        ),
        ArticleAnalysis(
            article_id="a2",
            entities=[
                _entity("person:elon-musk", "Elon Musk", EntityType.PERSON, 1),
                _entity("org:tesla", "Tesla", EntityType.ORG, 1),
            ],
            relations=[_relation("org:tesla", "person:elon-musk")],
        ),
    ]

    batch = build_batch(articles, analyses)

    assert len(batch.articles) == 2

    # Entities de-duplicated across the batch; longest name wins.
    entities = {e.canonical_id: e for e in batch.entities}
    assert set(entities) == {"person:elon-musk", "org:tesla"}
    assert entities["person:elon-musk"].name == "Elon Musk"
    assert entities["person:elon-musk"].type == "PERSON"

    # One MENTIONED_IN per (entity, article).
    assert len(batch.mentions) == 4
    musk_a1 = next(
        m for m in batch.mentions if m.entity_id == "person:elon-musk" and m.url.endswith("/a")
    )
    assert musk_a1.count == 2

    # Pair co-occurs in both articles -> weight 2.
    assert len(batch.cooccurrences) == 1
    edge = batch.cooccurrences[0]
    assert (edge.source_id, edge.target_id) == ("org:tesla", "person:elon-musk")
    assert edge.weight == 2


def test_build_batch_skips_analysis_without_article():
    analyses = [ArticleAnalysis(article_id="missing", entities=[], relations=[])]
    batch = build_batch([], analyses)
    assert batch.is_empty()


def test_build_batch_ignores_self_pairs():
    articles = [_article("a1", "https://x.com/a")]
    analyses = [
        ArticleAnalysis(
            article_id="a1",
            entities=[_entity("org:tesla", "Tesla", EntityType.ORG, 1)],
            relations=[_relation("org:tesla", "org:tesla")],
        )
    ]
    batch = build_batch(articles, analyses)
    assert batch.cooccurrences == []
