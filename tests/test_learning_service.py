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


def test_scope_tag_roundtrip():
    tagged = f"teach planets {learning_service.scope_tag('notebook:abc')}"
    text, nb = learning_service.split_scope_tag(tagged)
    assert text == "teach planets" and nb == "notebook:abc"
    assert learning_service.split_scope_tag("no tag") == ("no tag", None)
    assert learning_service.split_scope_tag("x [nb:abc]")[1] == "notebook:abc"


@pytest.mark.asyncio
async def test_searxng_shape_scopes_and_falls_back_to_text():
    calls = []

    async def vec(q, n, notebook_ids=None, **kw):
        calls.append(("vector", q, notebook_ids))
        return []

    async def txt(q, n, notebook_ids=None, **kw):
        calls.append(("text", q, notebook_ids))
        return [{"id": "note:1", "title": "Ceres", "matches": ["940 km across"], "similarity": 0.9}]

    async def no_active():
        return None

    with patch("open_notebook.domain.notebook.vector_search", vec), patch(
        "open_notebook.domain.notebook.text_search", txt
    ), patch.object(learning_service, "_active_learning_scope", no_active):
        out = await learning_service.notebook_search_as_searxng("ceres size [nb:notebook:n1]", 5)
    assert calls == [("vector", "ceres size", ["notebook:n1"]), ("text", "ceres size", ["notebook:n1"])]
    assert out["number_of_results"] == 1
    r = out["results"][0]
    assert r["title"] == "Ceres (note)" and r["content"] == "940 km across" and r["url"].endswith("/api/learn/ref/note:1")


@pytest.mark.asyncio
async def test_progress_merges_and_spaces_reviews():
    session = LearningSession(id="learning_session:1", notebook="notebook:n", title="t", requirement="r", status="succeeded")

    async def get(_id, refresh=False):
        return session

    saved = []

    async def save(self):
        saved.append(dict(self.learner or {}))

    with patch.object(learning_service, "get_learning_session", get), patch.object(LearningSession, "save", save):
        s1 = await learning_service.update_learning_progress("x", {"scene_index": 1, "scenes_seen": ["a"]})
        assert s1.learner["scene_index"] == 1 and s1.learner["scenes_seen"] == ["a"]
        s2 = await learning_service.update_learning_progress("x", {"scenes_seen": ["b", "a"], "quiz": {"q": {"correct": 1, "total": 4, "wrong": ["1", "2", "3"]}}})
        assert s2.learner["scenes_seen"] == ["a", "b"] and s2.quiz_score == 0.25
        s3 = await learning_service.update_learning_progress("x", {"completed": True})
        assert s3.completed_at and s3.review_due_at
        # poor score => shortest interval (1 day)
        assert (s3.review_due_at - s3.completed_at).days == 1
        s4 = await learning_service.update_learning_progress("x", {"quiz": {"q": {"correct": 4, "total": 4, "wrong": []}}, "completed": True})
        assert s4.quiz_score == 1.0 and s4.learner["reviews_done"] == 1
        assert (s4.review_due_at - s4.completed_at).days == 3  # second pass, good score => next interval
        s5 = await learning_service.update_learning_progress("x", {"completed": False})
        assert s5.completed_at is None and s5.review_due_at is None
    assert len(saved) == 5
