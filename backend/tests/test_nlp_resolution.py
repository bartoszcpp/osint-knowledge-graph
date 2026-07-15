"""Tests for primitive in-article entity resolution."""

from __future__ import annotations

from app.nlp.resolution import resolve_entities
from app.schemas.analysis import EntityMention, EntityType


def _mention(text: str, etype: EntityType, sent: int = 0) -> EntityMention:
    return EntityMention(
        text=text,
        type=etype,
        start_char=0,
        end_char=len(text),
        paragraph_index=0,
        sentence_index=sent,
    )


def test_person_variants_collapse_to_one_entity():
    mentions = [
        _mention("Elon Musk", EntityType.PERSON),
        _mention("Musk", EntityType.PERSON),
        _mention("E. Musk", EntityType.PERSON),
    ]
    entities, surface_to_id = resolve_entities(mentions)

    assert len(entities) == 1
    entity = entities[0]
    assert entity.type is EntityType.PERSON
    assert entity.name == "Elon Musk"  # canonical = longest surface form
    assert entity.canonical_id == "person:elon-musk"
    assert entity.mention_count == 3
    assert set(entity.surface_forms) == {"Elon Musk", "Musk", "E. Musk"}
    # Every surface form maps back to the same canonical id.
    assert set(surface_to_id.values()) == {"person:elon-musk"}


def test_distinct_people_with_same_surname_stay_separate():
    mentions = [
        _mention("Joe Biden", EntityType.PERSON),
        _mention("Hunter Biden", EntityType.PERSON),
    ]
    entities, _ = resolve_entities(mentions)
    assert len(entities) == 2


def test_org_subset_and_acronym_merge():
    mentions = [
        _mention("European Union", EntityType.ORG),
        _mention("EU", EntityType.ORG),
    ]
    entities, _ = resolve_entities(mentions)
    assert len(entities) == 1
    assert entities[0].name == "European Union"

    subset = [
        _mention("Tesla Inc", EntityType.ORG),
        _mention("Tesla", EntityType.ORG),
    ]
    entities2, _ = resolve_entities(subset)
    assert len(entities2) == 1


def test_types_are_not_merged_across_labels():
    mentions = [
        _mention("Washington", EntityType.PERSON),
        _mention("Washington", EntityType.GPE),
    ]
    entities, _ = resolve_entities(mentions)
    assert len(entities) == 2
    assert {e.type for e in entities} == {EntityType.PERSON, EntityType.GPE}
