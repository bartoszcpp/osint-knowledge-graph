"""Tests for the NLP processor orchestrator (spaCy stubbed out)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.nlp import pipeline, processor
from app.schemas.analysis import EntityMention, EntityType
from app.schemas.article import Article, SourceType


def _fake_mentions(_text: str) -> list[EntityMention]:
    def m(text, etype, sent):
        return EntityMention(
            text=text, type=etype, start_char=0, end_char=1, paragraph_index=0, sentence_index=sent
        )

    return [
        m("Angela Merkel", EntityType.PERSON, 0),
        m("Germany", EntityType.GPE, 0),
        m("Merkel", EntityType.PERSON, 1),
        m("European Union", EntityType.ORG, 1),
    ]


def test_process_article_produces_resolved_entities_and_relations(monkeypatch):
    monkeypatch.setattr(pipeline, "extract_all_mentions", _fake_mentions)

    article = Article.from_source(
        source=SourceType.GDELT,
        url="https://example.com/story",
        published_at=datetime(2026, 7, 15, tzinfo=UTC),
        title="Merkel and the EU",
        text_content="Angela Merkel met leaders. Germany and the European Union responded.",
    )

    analysis = processor.process_article(article)

    assert analysis.article_id == article.id
    names = {e.name for e in analysis.entities}
    # "Angela Merkel" + "Merkel" collapse into one PERSON entity.
    assert "Angela Merkel" in names
    assert len([e for e in analysis.entities if e.type is EntityType.PERSON]) == 1
    assert analysis.relations  # at least one co-occurrence edge was found


def test_build_text_separates_title_and_body():
    article = Article.model_construct(
        id="x", source=SourceType.REDDIT, url="https://e.com", title="Title", text_content="Body"
    )
    assert processor.build_text(article) == "Title\n\nBody"
