"""Unit tests for the Learn feature service (no DB / network)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import learning_service
from open_notebook.domain.learning import LearningSession


def _notebook(sources=None, notes=None):
    nb = MagicMock()
    nb.id = "notebook:test"
    nb.name = "Cells"
    nb.description = "Biology basics"
    nb.get_sources = AsyncMock(return_value=sources or [])
    nb.get_notes = AsyncMock(return_value=notes or [])
    return nb


def _source(id_, title, text, topics=None):
    s = MagicMock()
    s.id, s.title, s.full_text, s.topics = id_, title, text, topics or []
    return s


def _note(title, content):
    n = MagicMock()
    n.title, n.content = title, content
    return n


@pytest.mark.asyncio
async def test_bundle_includes_sources_insights_and_notes():
    nb = _notebook(
        sources=[_source("source:1", "Mitochondria", "Powerhouse of the cell.", ["energy"])],
        notes=[_note("Recap", "Cells have organelles."), _note("Empty", None)],
    )
    insight = MagicMock()
    insight.insight_type, insight.content = "summary", "Mitochondria make ATP."
    with patch.object(
        learning_service.SourceInsight,
        "get_for_sources",
        AsyncMock(return_value={"source:1": [insight]}),
    ):
        bundle = await learning_service.build_material_bundle(nb)

    text, stats = bundle["text"], bundle["stats"]
    assert "# Notebook: Cells" in text
    assert "## Source: Mitochondria" in text
    assert "Topics: energy" in text
    assert "### Insight (summary)" in text and "Mitochondria make ATP." in text
    assert "Powerhouse of the cell." in text
    assert "## Note: Recap" in text
    assert "Empty" not in text  # notes without content are skipped
    assert stats == {"sources": 1, "insights": 1, "notes": 1, "truncated": False, "chars": len(text)}


@pytest.mark.asyncio
async def test_bundle_respects_toggles_and_truncates():
    nb = _notebook(
        sources=[_source("source:1", "Long", "x" * 5000)],
        notes=[_note("N", "y" * 5000)],
    )
    with patch.object(
        learning_service.SourceInsight, "get_for_sources", AsyncMock(return_value={})
    ):
        bundle = await learning_service.build_material_bundle(
            nb, include_insights=False, include_notes=False, max_chars=1000
        )
    assert bundle["stats"]["notes"] == 0
    assert bundle["stats"]["truncated"] is True
    assert "[... truncated" in bundle["text"]
    assert bundle["stats"]["chars"] < 1100


def test_learning_session_save_data_keeps_record_link():
    s = LearningSession(notebook="notebook:abc", title="t", requirement="r")
    data = s._prepare_save_data()
    assert str(data["notebook"]) == "notebook:abc"
    assert not isinstance(data["notebook"], str)
    assert s.notebook_id == "notebook:abc"


def test_openmaic_url_defaults(monkeypatch):
    monkeypatch.delenv("OPENMAIC_URL", raising=False)
    monkeypatch.delenv("OPENMAIC_PUBLIC_URL", raising=False)
    assert learning_service.openmaic_url() == "http://localhost:3100"
    monkeypatch.setenv("OPENMAIC_URL", "http://openmaic:3100/")
    monkeypatch.setenv("OPENMAIC_PUBLIC_URL", "https://learn.example.com/")
    assert learning_service.openmaic_url() == "http://openmaic:3100"
    assert learning_service.public_openmaic_url() == "https://learn.example.com"
