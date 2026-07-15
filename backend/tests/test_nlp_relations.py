"""Tests for co-occurrence relation detection."""

from __future__ import annotations

from app.nlp.relations import detect_relations
from app.nlp.resolution import resolve_entities
from app.schemas.analysis import EntityMention, EntityType


def _mention(text: str, etype: EntityType, sent: int, para: int = 0) -> EntityMention:
    return EntityMention(
        text=text,
        type=etype,
        start_char=0,
        end_char=len(text),
        paragraph_index=para,
        sentence_index=sent,
    )


def _relation_lookup(relations):
    return {tuple(sorted((r.source_id, r.target_id))): r for r in relations}


def test_sentence_cooccurrence_creates_weighted_edges():
    mentions = [
        # sentence 0: Musk + Tesla
        _mention("Elon Musk", EntityType.PERSON, sent=0),
        _mention("Tesla", EntityType.ORG, sent=0),
        # sentence 1: Musk + SpaceX
        _mention("Musk", EntityType.PERSON, sent=1),
        _mention("SpaceX", EntityType.ORG, sent=1),
        # sentence 2: Musk + Tesla again -> strengthens that edge
        _mention("Musk", EntityType.PERSON, sent=2),
        _mention("Tesla", EntityType.ORG, sent=2),
    ]
    entities, surface_to_id = resolve_entities(mentions)
    relations = detect_relations(mentions, surface_to_id, entities, scope="sentence")

    lookup = _relation_lookup(relations)
    musk_tesla = lookup[("org:tesla", "person:elon-musk")]
    musk_spacex = lookup[("org:spacex", "person:elon-musk")]

    assert musk_tesla.weight == 2  # co-occur in sentences 0 and 2
    assert musk_spacex.weight == 1
    assert len(relations) == 2  # no Tesla<->SpaceX edge (never in same sentence)


def test_paragraph_scope_links_entities_across_sentences():
    mentions = [
        _mention("Tesla", EntityType.ORG, sent=0, para=0),
        _mention("SpaceX", EntityType.ORG, sent=1, para=0),
    ]
    entities, surface_to_id = resolve_entities(mentions)

    sentence_rel = detect_relations(mentions, surface_to_id, entities, scope="sentence")
    paragraph_rel = detect_relations(mentions, surface_to_id, entities, scope="paragraph")

    assert sentence_rel == []  # different sentences -> no sentence-scope edge
    assert len(paragraph_rel) == 1  # same paragraph -> linked
    assert paragraph_rel[0].weight == 1
