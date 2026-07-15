"""Primitive in-article entity resolution (deduplication).

Within a single article we want "Elon Musk", "Musk" and "E. Musk" to collapse to
one node. This is a deliberately simple, rule-based resolver (no ML linking):

- normalize surface forms (case, punctuation, possessives),
- cluster mentions of the same type greedily, longest-first,
- treat a shorter mention as the same entity when its tokens are a subset of a
  longer one, when surnames match (with initial expansion) for people, or when
  an acronym matches for orgs/GPEs.

It is scoped to one article, exactly as required for the MVP.
"""

from __future__ import annotations

import re
from collections import Counter

from app.schemas.analysis import EntityMention, EntityType, ResolvedEntity, canonical_id

_POSSESSIVE_RE = re.compile(r"[’']s\b")
_KEEP_CHARS_RE = re.compile(r"[^a-z0-9 .-]")
_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, strip possessives/punctuation, collapse whitespace."""
    t = text.lower().strip()
    t = _POSSESSIVE_RE.sub("", t)
    t = _KEEP_CHARS_RE.sub(" ", t)  # keep dots (initials) and hyphens
    return _WS_RE.sub(" ", t).strip()


def _tokens(norm: str) -> list[str]:
    return [tok for tok in re.split(r"[ .]+", norm) if tok]


def _is_initial_of(short: str, full: str) -> bool:
    """True if `short` is an initial for `full` (e.g. 'e' -> 'elon')."""
    return len(short) == 1 and full.startswith(short)


def _person_compatible(tokens: list[str], canonical_tokens: list[str]) -> bool:
    if not tokens or not canonical_tokens:
        return False
    # Subset of the canonical name's tokens: "musk" in {"elon", "musk"}.
    if set(tokens).issubset(set(canonical_tokens)):
        return True
    # Surname match, allowing initials on the given names ("E. Musk" ~ "Elon Musk").
    if tokens[-1] != canonical_tokens[-1]:
        return False
    given, canonical_given = tokens[:-1], canonical_tokens[:-1]
    if len(given) > len(canonical_given):
        return False
    return all(
        g == c or _is_initial_of(g, c) or _is_initial_of(c, g)
        for g, c in zip(given, canonical_given, strict=False)
    )


def _acronym(tokens: list[str]) -> str:
    return "".join(tok[0] for tok in tokens if tok)


def _org_compatible(tokens: list[str], canonical_tokens: list[str]) -> bool:
    if not tokens or not canonical_tokens:
        return False
    if set(tokens).issubset(set(canonical_tokens)):
        return True
    # Acronym match: "eu" ~ "European Union", "un" ~ "United Nations".
    if len(tokens) == 1 and len(canonical_tokens) > 1:
        return tokens[0] == _acronym(canonical_tokens)
    return False


def _compatible(etype: EntityType, tokens: list[str], canonical_tokens: list[str]) -> bool:
    if etype is EntityType.PERSON:
        return _person_compatible(tokens, canonical_tokens)
    return _org_compatible(tokens, canonical_tokens)


class _Cluster:
    __slots__ = ("canonical_tokens", "display", "norms", "surfaces", "count")

    def __init__(self, norm: str, display: str, count: int):
        self.canonical_tokens = _tokens(norm)
        self.display = display
        self.norms = {norm}
        self.surfaces: dict[str, None] = {display: None}  # ordered set
        self.count = count


def resolve_entities(
    mentions: list[EntityMention],
) -> tuple[list[ResolvedEntity], dict[tuple[EntityType, str], str]]:
    """Resolve mentions into de-duplicated entities.

    Returns the resolved entities plus a lookup mapping ``(type, normalized
    surface) -> canonical_id`` so relation detection can map any mention back to
    its entity.
    """
    by_type: dict[EntityType, Counter[str]] = {}
    display_for: dict[tuple[EntityType, str], str] = {}
    for m in mentions:
        norm = normalize(m.text)
        if not norm:
            continue
        by_type.setdefault(m.type, Counter())[norm] += 1
        display_for.setdefault((m.type, norm), m.text.strip())

    entities: list[ResolvedEntity] = []
    surface_to_id: dict[tuple[EntityType, str], str] = {}

    for etype, counts in by_type.items():
        # Longest (most tokens, then longest string) first so canonicals win.
        ordered = sorted(counts, key=lambda n: (len(_tokens(n)), len(n)), reverse=True)
        clusters: list[_Cluster] = []

        for norm in ordered:
            tokens = _tokens(norm)
            display = display_for[(etype, norm)]
            for cluster in clusters:
                if _compatible(etype, tokens, cluster.canonical_tokens):
                    cluster.norms.add(norm)
                    cluster.surfaces.setdefault(display, None)
                    cluster.count += counts[norm]
                    break
            else:
                clusters.append(_Cluster(norm, display, counts[norm]))

        for cluster in clusters:
            cid = canonical_id(etype, cluster.display)
            entities.append(
                ResolvedEntity(
                    canonical_id=cid,
                    name=cluster.display,
                    type=etype,
                    surface_forms=list(cluster.surfaces),
                    mention_count=cluster.count,
                )
            )
            for norm in cluster.norms:
                surface_to_id[(etype, norm)] = cid

    return entities, surface_to_id
