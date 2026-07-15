"""NLP analysis schemas.

The output of the NER pipeline: mentions found in text, the resolved (de-duped)
entities they map to, and the co-occurrence relations between those entities.
These are source-agnostic and feed both Postgres (Phase 3) and the Neo4j graph
(Phase 4).
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field


class EntityType(StrEnum):
    """spaCy entity labels we track (mapped 1:1 from spaCy's NER labels)."""

    PERSON = "PERSON"  # people, incl. fictional
    ORG = "ORG"  # companies, agencies, institutions
    GPE = "GPE"  # geo-political entities: countries, cities, states


#: spaCy labels kept by the pipeline. Everything else is discarded.
TRACKED_LABELS: frozenset[str] = frozenset(e.value for e in EntityType)


def canonical_id(entity_type: EntityType | str, name: str) -> str:
    """Stable id for an entity, e.g. ``person:elon-musk``.

    Deriving the id purely from (type, normalized name) means the same entity
    referenced in different articles naturally collapses onto one id when stored
    - a light form of cross-article resolution on top of the in-article dedup.
    """
    type_value = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{type_value.lower()}:{slug}"


class EntityMention(BaseModel):
    """A single surface-form occurrence of an entity in the text."""

    text: str
    type: EntityType
    start_char: int
    end_char: int
    paragraph_index: int
    sentence_index: int


class ResolvedEntity(BaseModel):
    """A de-duplicated entity: one node per real-world thing within an article."""

    canonical_id: str
    name: str  # canonical display form (usually the longest mention)
    type: EntityType
    surface_forms: list[str] = Field(default_factory=list)
    mention_count: int = 0


class Relation(BaseModel):
    """An undirected co-occurrence link between two resolved entities."""

    source_id: str
    target_id: str
    source_name: str
    target_name: str
    source_type: EntityType
    target_type: EntityType
    weight: int = 1  # number of co-occurrences within the chosen scope
    scope: str = "sentence"


class ArticleAnalysis(BaseModel):
    """Full NLP result for one article."""

    article_id: str
    entities: list[ResolvedEntity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
