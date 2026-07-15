"""End-to-end NLP processing: Article -> ArticleAnalysis.

Ties the three stages together:
1. NER: extract PERSON/ORG/GPE mentions (spaCy),
2. resolution: de-duplicate mentions into entities within the article,
3. relations: build co-occurrence edges between those entities.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.nlp import pipeline, relations, resolution
from app.schemas.analysis import ArticleAnalysis
from app.schemas.article import Article

logger = get_logger(__name__)


def build_text(article: Article) -> str:
    """Combine the fields worth running NER over into one document.

    Title and body are separated by a blank line so they land in different
    paragraphs (and thus never spuriously co-occur across the boundary).
    """
    parts = [part for part in (article.title, article.text_content) if part and part.strip()]
    return "\n\n".join(parts)


def analyze_text(article_id: str, text: str) -> ArticleAnalysis:
    """Run the full NLP pipeline over raw text (no DB access)."""
    mentions = pipeline.extract_all_mentions(text)
    entities, surface_to_id = resolution.resolve_entities(mentions)
    rels = relations.detect_relations(
        mentions, surface_to_id, entities, scope=settings.nlp_cooccurrence_scope
    )
    return ArticleAnalysis(article_id=article_id, entities=entities, relations=rels)


def process_article(article: Article) -> ArticleAnalysis:
    """Analyze a stored article into resolved entities and relations."""
    analysis = analyze_text(article.id, build_text(article))
    logger.info(
        "Analyzed article %s: %d entit(y/ies), %d relation(s)",
        article.id,
        len(analysis.entities),
        len(analysis.relations),
    )
    return analysis
