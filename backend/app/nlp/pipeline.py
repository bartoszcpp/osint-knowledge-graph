"""spaCy pipeline: model loading and raw entity extraction.

Loads the configured spaCy model once (cached) and turns text into a list of
:class:`EntityMention` objects for the tracked labels (PERSON / ORG / GPE).

The model is loaded lazily on first use so importing this module (which happens
in every Celery worker via task discovery) does not pull spaCy into memory unless
NER actually runs.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.analysis import TRACKED_LABELS, EntityMention, EntityType

if TYPE_CHECKING:
    from spacy.language import Language

logger = get_logger(__name__)

# Components irrelevant to NER + sentence segmentation. Disabling them keeps the
# CPU-heavy path lean (we still need the parser for `doc.sents`).
_DISABLE = ("lemmatizer", "tagger", "attribute_ruler")

# Split on blank lines first; the pipeline processes each paragraph separately so
# sentence indices are paragraph-local.
_PARAGRAPH_RE = re.compile(r"\n\s*\n+")


@lru_cache(maxsize=1)
def get_nlp() -> Language:
    """Return the cached spaCy model, loading it on first call."""
    import spacy  # lazy: keeps spaCy out of memory until NER is needed

    model = settings.spacy_model
    logger.info("Loading spaCy model: %s", model)
    try:
        return spacy.load(model, disable=list(_DISABLE))
    except OSError as exc:  # model not installed
        raise RuntimeError(
            f"spaCy model '{model}' is not installed. Run: python -m spacy download {model}"
        ) from exc


def split_paragraphs(text: str) -> list[str]:
    """Split text into non-empty paragraphs."""
    return [p.strip() for p in _PARAGRAPH_RE.split(text) if p.strip()]


def extract_mentions(text: str, paragraph_index: int = 0) -> list[EntityMention]:
    """Extract PERSON/ORG/GPE mentions from a single paragraph of text."""
    if not text.strip():
        return []

    doc = get_nlp()(text)
    mentions: list[EntityMention] = []
    for sentence_index, sent in enumerate(doc.sents):
        for ent in sent.ents:
            if ent.label_ not in TRACKED_LABELS:
                continue
            mentions.append(
                EntityMention(
                    text=ent.text,
                    type=EntityType(ent.label_),
                    start_char=ent.start_char,
                    end_char=ent.end_char,
                    paragraph_index=paragraph_index,
                    sentence_index=sentence_index,
                )
            )
    return mentions


def extract_all_mentions(text: str) -> list[EntityMention]:
    """Extract mentions across the whole text, paragraph by paragraph."""
    mentions: list[EntityMention] = []
    for paragraph_index, paragraph in enumerate(split_paragraphs(text)):
        mentions.extend(extract_mentions(paragraph, paragraph_index))
    return mentions
