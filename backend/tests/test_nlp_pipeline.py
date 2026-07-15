"""Integration test for the spaCy pipeline.

Skipped automatically when spaCy or the configured model is not installed, so the
rest of the suite stays fast and dependency-light.
"""

from __future__ import annotations

import pytest

pytest.importorskip("spacy")

from app.nlp import pipeline  # noqa: E402
from app.schemas.analysis import EntityType  # noqa: E402


@pytest.fixture(scope="module")
def _model_available() -> bool:
    try:
        pipeline.get_nlp()
    except RuntimeError:
        pytest.skip("spaCy model not installed")
    return True


def test_extract_mentions_finds_person_org_gpe(_model_available):
    text = "Tim Cook, the CEO of Apple, met officials in France."
    mentions = pipeline.extract_all_mentions(text)

    types = {m.type for m in mentions}
    texts = {m.text for m in mentions}

    assert EntityType.PERSON in types
    assert any("Apple" in t for t in texts)
    assert any(m.type is EntityType.GPE for m in mentions)
