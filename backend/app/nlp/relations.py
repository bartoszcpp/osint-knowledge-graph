"""Co-occurrence relation detection (MVP).

If two distinct resolved entities appear within the same scope (sentence or
paragraph), we treat that as a potential link. The relation weight is the number
of scopes in which the pair co-occurs, so entities mentioned together repeatedly
get a stronger edge.

Relations are undirected: the pair is stored with ids sorted so ``(A, B)`` and
``(B, A)`` collapse to one edge.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations

from app.nlp.resolution import normalize
from app.schemas.analysis import EntityMention, EntityType, Relation, ResolvedEntity


def detect_relations(
    mentions: list[EntityMention],
    surface_to_id: dict[tuple[EntityType, str], str],
    entities: list[ResolvedEntity],
    scope: str = "sentence",
) -> list[Relation]:
    """Build weighted co-occurrence relations between resolved entities."""
    entities_by_id = {e.canonical_id: e for e in entities}

    # Group the canonical ids present in each scope unit.
    groups: dict[tuple[int, ...], set[str]] = defaultdict(set)
    for m in mentions:
        cid = surface_to_id.get((m.type, normalize(m.text)))
        if cid is None:
            continue
        key = (m.paragraph_index, m.sentence_index) if scope == "sentence" else (m.paragraph_index,)
        groups[key].add(cid)

    weights: Counter[tuple[str, str]] = Counter()
    for ids in groups.values():
        for a, b in combinations(sorted(ids), 2):
            weights[(a, b)] += 1

    relations: list[Relation] = []
    for (a, b), weight in weights.items():
        ea, eb = entities_by_id[a], entities_by_id[b]
        relations.append(
            Relation(
                source_id=a,
                target_id=b,
                source_name=ea.name,
                target_name=eb.name,
                source_type=ea.type,
                target_type=eb.type,
                weight=weight,
                scope=scope,
            )
        )
    return relations
