"""
Learn feature service: turn a notebook into an interactive OpenMAIC classroom.

OpenMAIC (vendor/openmaic) runs as a sidecar Next.js service (OPENMAIC_URL,
default http://localhost:3100). We bundle the notebook's sources, insights and
notes into a text corpus, submit it to OpenMAIC's `POST /api/generate-classroom`
job API, and track the job on a `learning_session` record.
"""

import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from loguru import logger

from open_notebook.domain.learning import LearningSession
from open_notebook.domain.notebook import Notebook, SourceInsight
from open_notebook.exceptions import (
    ConfigurationError,
    ExternalServiceError,
    InvalidInputError,
    NotFoundError,
)

# OpenMAIC keeps the whole corpus in the prompt of every generation stage;
# keep it well under typical 128k-token windows.
DEFAULT_MAX_MATERIAL_CHARS = int(os.getenv("OPENMAIC_MAX_MATERIAL_CHARS", "120000"))
PER_SOURCE_CHARS = int(os.getenv("OPENMAIC_PER_SOURCE_CHARS", "30000"))
LIVE_RETRIEVAL_MATERIAL_CHARS = int(os.getenv("OPENMAIC_LIVE_MATERIAL_CHARS", "40000"))


def open_notebook_internal_url() -> str:
    """URL OpenMAIC (same host) uses to call back into this API."""
    return os.getenv("OPEN_NOTEBOOK_INTERNAL_URL", f"http://127.0.0.1:{os.getenv('API_PORT', '5055')}").rstrip("/")


SCOPE_TAG = re.compile(r"\[nb:([A-Za-z0-9_:\-]+)\]")


def scope_tag(notebook_id: str) -> str:
    return f"[nb:{notebook_id}]"


def split_scope_tags(text: str) -> Tuple[str, List[str]]:
    """Return (text without tags, notebook ids) — tags may have been rewritten away."""
    ids = []
    for m in SCOPE_TAG.finditer(text or ""):
        nb = m.group(1)
        ids.append(nb if nb.startswith("notebook:") else f"notebook:{nb}")
    return (SCOPE_TAG.sub("", text).strip() if ids else text), ids


def split_scope_tag(text: str) -> Tuple[str, Optional[str]]:
    """Single-notebook convenience over split_scope_tags."""
    clean, ids = split_scope_tags(text)
    return clean, (ids[0] if ids else None)


def openmaic_url() -> str:
    return os.getenv("OPENMAIC_URL", "http://localhost:3100").rstrip("/")


def public_openmaic_url() -> str:
    """URL the browser should use (may differ from the server-side one)."""
    return os.getenv("OPENMAIC_PUBLIC_URL", openmaic_url()).rstrip("/")


def _headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    code = os.getenv("OPENMAIC_ACCESS_CODE")
    if code:
        headers["x-access-code"] = code
    return headers


async def openmaic_health() -> Dict[str, Any]:
    url = openmaic_url()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{url}/api/health")
            return {
                "available": r.status_code < 500,
                "url": url,
                "public_url": public_openmaic_url(),
                "status_code": r.status_code,
            }
    except Exception as e:  # noqa: BLE001
        return {"available": False, "url": url, "public_url": public_openmaic_url(), "error": str(e)}


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[... truncated {len(text) - limit} characters ...]"


async def build_material_bundle(
    notebook: Notebook,
    include_sources: bool = True,
    include_insights: bool = True,
    include_notes: bool = True,
    max_chars: int = DEFAULT_MAX_MATERIAL_CHARS,
) -> Dict[str, Any]:
    """Collect the notebook's content into a single text corpus for OpenMAIC."""
    parts: List[str] = [f"# Notebook: {notebook.name}\n\n{notebook.description or ''}".strip()]
    stats = {"sources": 0, "insights": 0, "notes": 0, "truncated": False}

    if include_sources or include_insights:
        sources = await notebook.get_sources(include_full_text=include_sources)
        insights_by_source: Dict[str, List[SourceInsight]] = {}
        if include_insights and sources:
            insights_by_source = await SourceInsight.get_for_sources(
                [str(s.id) for s in sources]
            )
        for source in sources:
            block = [f"\n\n## Source: {source.title or 'Untitled'}"]
            if source.topics:
                block.append(f"Topics: {', '.join(source.topics)}")
            src_insights = insights_by_source.get(str(source.id), [])
            for ins in src_insights:
                block.append(f"\n### Insight ({ins.insight_type})\n{ins.content}")
                stats["insights"] += 1
            if include_sources and source.full_text:
                block.append(f"\n### Content\n{_truncate(source.full_text, PER_SOURCE_CHARS)}")
            stats["sources"] += 1
            parts.append("\n".join(block))

    if include_notes:
        notes = await notebook.get_notes(include_content=True)
        for note in notes:
            if not note.content:
                continue
            parts.append(f"\n\n## Note: {note.title or 'Untitled'}\n{note.content}")
            stats["notes"] += 1

    text = "\n".join(parts)
    if len(text) > max_chars:
        text = _truncate(text, max_chars)
        stats["truncated"] = True
    stats["chars"] = len(text)
    return {"text": text, "stats": stats}


async def create_learning_session(
    notebook_id: str,
    requirement: Optional[str] = None,
    title: Optional[str] = None,
    include_sources: bool = True,
    include_insights: bool = True,
    include_notes: bool = True,
    enable_tts: bool = False,
    enable_image_generation: bool = False,
    enable_web_search: bool = False,
    live_retrieval: bool = True,
) -> LearningSession:
    notebook = await Notebook.get(notebook_id)
    if not notebook:
        raise NotFoundError(f"Notebook {notebook_id} not found")

    # With live retrieval the classroom can pull details on demand, so the static bundle only
    # needs to be an overview: cap it lower to leave prompt room for the retrieved passages.
    max_chars = LIVE_RETRIEVAL_MATERIAL_CHARS if live_retrieval else DEFAULT_MAX_MATERIAL_CHARS
    bundle = await build_material_bundle(
        notebook, include_sources, include_insights, include_notes, max_chars=max_chars
    )
    if bundle["stats"]["sources"] + bundle["stats"]["notes"] == 0:
        raise InvalidInputError("Notebook has no sources or notes to learn from")

    requirement = (requirement or "").strip() or (
        f"Create an engaging, well-structured lesson that teaches the key ideas in the "
        f"notebook \"{notebook.name}\". Base every slide strictly on the provided materials, "
        f"include a short quiz to check understanding, and finish with a summary."
    )
    session = LearningSession(
        notebook=notebook_id,
        title=title or f"Learn: {notebook.name}",
        requirement=requirement,
        status="pending",
        options={
            "include_sources": include_sources,
            "include_insights": include_insights,
            "include_notes": include_notes,
            "enable_tts": enable_tts,
            "enable_image_generation": enable_image_generation,
            "enable_web_search": enable_web_search,
            "live_retrieval": live_retrieval,
        },
        material_stats=bundle["stats"],
    )
    await session.save()

    return await _submit_classroom(
        session,
        material_text=bundle["text"],
        scope=scope_tag(notebook_id) if live_retrieval else None,
        enable_tts=enable_tts,
        enable_image_generation=enable_image_generation,
        enable_web_search=enable_web_search,
    )


async def create_learning_session_from_question(
    question: str,
    notebook_ids: Optional[List[str]] = None,
    title: Optional[str] = None,
    enable_tts: bool = True,
    limit: int = 12,
) -> LearningSession:
    """Build a classroom that answers a question, from the best-matching passages across the
    selected notebooks (or the whole knowledge base) — the "Learn" action on Ask & Search."""
    from open_notebook.domain.notebook import text_search, vector_search

    question = (question or "").strip()
    if not question:
        raise InvalidInputError("A question is required")
    scope = [n for n in (notebook_ids or []) if n] or None
    try:
        rows = await vector_search(question, limit, notebook_ids=scope)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Learn-from-question: vector search failed ({e}); using text search")
        rows = []
    if not rows:
        rows = await text_search(question, limit, notebook_ids=scope)
    if not rows:
        raise InvalidInputError("Nothing in the selected notebooks matches that question")

    parts = [f"# Question\n\n{question}\n\n# Relevant material"]
    for row in rows:
        matches = row.get("matches") or []
        body = "\n".join(m for m in matches if isinstance(m, str)) if isinstance(matches, list) else str(matches)
        parts.append(f"\n\n## {row.get('title') or 'Untitled'}\n{_truncate(body, PER_SOURCE_CHARS)}")
    material = _truncate("\n".join(parts), LIVE_RETRIEVAL_MATERIAL_CHARS)

    names = await notebook_names(scope or [])
    scope_label = ", ".join(names.values()) if names else "the knowledge base"
    requirement = (
        f'Create a focused lesson that answers the question: "{question}". Teach the underlying '
        f"concepts needed to understand the answer, base every slide strictly on the provided "
        f"materials, include a short quiz, and finish with a concise summary of the answer."
    )
    session = LearningSession(
        notebook=scope[0] if scope and len(scope) == 1 else None,
        scope_notebooks=list(scope) if scope else None,
        question=question,
        title=title or f"Learn: {question[:80]}",
        requirement=requirement,
        status="pending",
        options={"from_question": True, "enable_tts": enable_tts, "live_retrieval": True, "scope": scope_label},
        material_stats={"sources": len(rows), "insights": 0, "notes": 0, "chars": len(material), "truncated": False},
    )
    await session.save()
    # live retrieval scoped to the same notebooks (one tag per notebook; unscoped = whole KB)
    tags = " ".join(scope_tag(n) for n in scope) if scope else ""
    return await _submit_classroom(session, material_text=material, scope=tags, enable_tts=enable_tts)


async def _submit_classroom(
    session: LearningSession,
    *,
    material_text: str,
    scope: Optional[str],
    enable_tts: bool = False,
    enable_image_generation: bool = False,
    enable_web_search: bool = False,
) -> LearningSession:
    """Submit the generation job to OpenMAIC and record the job on the session."""
    payload: Dict[str, Any] = {
        "requirement": session.requirement,
        "pdfContent": {"text": material_text, "images": []},
        "enableTTS": enable_tts,
        "enableImageGeneration": enable_image_generation,
        "enableVideoGeneration": False,
        "enableWebSearch": enable_web_search,
    }
    if scope is not None:
        # OpenMAIC's "web search" is pointed at Open Notebook: its keyless SearXNG provider is a
        # plain JSON GET, which /api/learn/searxng/search emulates (SEARXNG_BASE_URL in the sidecar
        # .env). The notebook scope travels inside the query as `[nb:<id>]` tags that the
        # requirement carries; the endpoint strips them and scopes the search. OpenMAIC is unmodified.
        payload["enableWebSearch"] = True
        payload["webSearchProviderId"] = "searxng"
        payload["requirement"] = f"{session.requirement} {scope}".strip()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{openmaic_url()}/api/generate-classroom", json=payload, headers=_headers()
            )
    except httpx.HTTPError as e:
        session.status = "failed"
        session.error = f"OpenMAIC unreachable at {openmaic_url()}: {e}"
        await session.save()
        raise ConfigurationError(session.error) from e

    if r.status_code >= 400:
        session.status = "failed"
        session.error = f"OpenMAIC returned {r.status_code}: {r.text[:500]}"
        await session.save()
        raise ExternalServiceError(session.error)

    data = r.json().get("data", r.json())
    session.job_id = data.get("jobId")
    session.status = "running"
    session.step = data.get("step")
    session.message = data.get("message")
    await session.save()
    logger.info(f"Learning session {session.id} submitted as OpenMAIC job {session.job_id}")
    return session


async def refresh_learning_session(session: LearningSession) -> LearningSession:
    """Poll OpenMAIC for job progress and persist any change."""
    if session.status in ("succeeded", "failed") or not session.job_id:
        return session
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{openmaic_url()}/api/generate-classroom/{session.job_id}", headers=_headers()
            )
    except httpx.HTTPError as e:
        logger.warning(f"Could not poll OpenMAIC job {session.job_id}: {e}")
        return session
    if r.status_code == 404:
        session.status = "failed"
        session.error = "OpenMAIC job not found (sidecar restarted before completion?)"
        await session.save()
        return session
    if r.status_code >= 400:
        logger.warning(f"OpenMAIC job poll {r.status_code}: {r.text[:200]}")
        return session

    body = r.json()
    data = body.get("data", body)
    status = data.get("status")
    session.step = data.get("step") or session.step
    session.message = data.get("message") or session.message
    if data.get("progress") is not None:
        session.progress = int(data["progress"])
    if status == "succeeded":
        result = data.get("result") or {}
        session.status = "succeeded"
        session.progress = 100
        session.classroom_id = result.get("classroomId") or result.get("id")
        # OpenMAIC builds `url` from the server-side request origin; rebuild it
        # for the browser so it works behind proxies / different hostnames.
        if session.classroom_id:
            session.classroom_url = f"{public_openmaic_url()}/classroom/{session.classroom_id}"
        else:
            session.classroom_url = result.get("url")
    elif status == "failed":
        session.status = "failed"
        session.error = data.get("error") or data.get("message") or "Generation failed"
    else:
        session.status = "running"
    await session.save()
    return session


async def list_learning_sessions(notebook_id: str, refresh: bool = True) -> List[LearningSession]:
    sessions = await LearningSession.for_notebook(notebook_id)
    if refresh:
        running = [s for s in sessions if s.status in ("pending", "running") and s.job_id]
        if running:
            await asyncio.gather(*(refresh_learning_session(s) for s in running))
    return sessions


async def list_all_learning_sessions(refresh: bool = True) -> List[LearningSession]:
    sessions = await LearningSession.all_recent()
    if refresh:
        running = [s for s in sessions if s.status in ("pending", "running") and s.job_id]
        if running:
            await asyncio.gather(*(refresh_learning_session(s) for s in running))
    return sessions


async def notebook_names(notebook_ids) -> Dict[str, str]:
    ids = [i for i in notebook_ids if i]
    if not ids:
        return {}
    from open_notebook.database.repository import ensure_record_id, repo_query

    rows = await repo_query(
        "SELECT id, name FROM notebook WHERE id IN $ids", {"ids": [ensure_record_id(i) for i in ids]}
    )
    return {str(r["id"]): r["name"] for r in rows or []}


async def get_learning_session(session_id: str, refresh: bool = True) -> LearningSession:
    session = await LearningSession.get(session_id)
    if not session:
        raise NotFoundError(f"Learning session {session_id} not found")
    return await refresh_learning_session(session) if refresh else session


async def delete_learning_session(session_id: str) -> None:
    session = await LearningSession.get(session_id)
    if not session:
        raise NotFoundError(f"Learning session {session_id} not found")
    await session.delete()


async def _active_learning_scope() -> Optional[List[str]]:
    """Notebook scope of the most recent running classroom job — OpenMAIC's query rewrite can
    drop the ``[nb:]`` tags, and only one classroom is generated at a time in practice.
    ``None`` means the job spans the whole knowledge base (or nothing is running)."""
    try:
        rows = await LearningSession.all_recent(limit=5)
    except Exception:  # noqa: BLE001
        return None
    for s in rows:
        if s.status in ("pending", "running"):
            if s.scope_notebooks:
                return [str(n) for n in s.scope_notebooks]
            return [s.notebook_id] if s.notebook_id else None
    return None


async def notebook_search_as_searxng(
    query: str, limit: int = 8, notebook_id: Optional[str] = None
) -> Dict[str, Any]:
    """Search a notebook (vector, falling back to text) and answer in SearXNG's JSON shape.

    The notebook comes from an explicit argument or a ``[nb:<id>]`` tag inside the query; without
    either, the search spans every notebook (the tag can be lost in OpenMAIC's query rewrite).
    """
    from open_notebook.domain.notebook import text_search, vector_search

    query, tagged = split_scope_tags((query or "").strip())
    if notebook_id:
        scope: Optional[List[str]] = [notebook_id]
    elif tagged:
        scope = tagged
    else:
        scope = await _active_learning_scope()
    if not query:
        return {"query": query, "number_of_results": 0, "results": []}
    try:
        rows = await vector_search(query, limit, notebook_ids=scope)
    except Exception as e:  # noqa: BLE001 - no embedding model, etc.
        logger.warning(f"Learn retrieval: vector search failed ({e}); using text search")
        rows = []
    if not rows:
        try:
            rows = await text_search(query, limit, notebook_ids=scope)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Learn retrieval: text search failed: {e}")
            rows = []
    results = []
    for i, row in enumerate(rows or []):
        rid = str(row.get("id") or row.get("parent_id") or "")
        matches = row.get("matches") or []
        content = "\n".join(m for m in matches if isinstance(m, str)) if isinstance(matches, list) else str(matches)
        kind = "note" if rid.startswith("note:") else "insight" if rid.startswith("source_insight:") else "source"
        results.append(
            {
                "title": f"{row.get('title') or 'Untitled'} ({kind})",
                # A stable, resolvable URL so OpenMAIC's URL registry/trust gate accepts it.
                "url": f"{open_notebook_internal_url()}/api/learn/ref/{rid}",
                "content": content[:2000],
                "score": float(row.get("similarity") or (1 - i * 0.05)),
            }
        )
    return {"query": query, "number_of_results": len(results), "results": results}


async def learn_reference(record_id: str) -> Dict[str, Any]:
    """Plain-text view of a source / note / insight for the sidecar's fetch_url tool."""
    from fastapi.responses import PlainTextResponse

    from open_notebook.domain.notebook import Note, Source, SourceInsight

    table = record_id.split(":", 1)[0]
    if table == "source":
        src = await Source.get(record_id)
        if not src:
            raise NotFoundError(record_id)
        body = f"# {src.title or 'Untitled'}\n\n{src.full_text or ''}"
    elif table == "note":
        note = await Note.get(record_id)
        if not note:
            raise NotFoundError(record_id)
        body = f"# {note.title or 'Untitled'}\n\n{note.content or ''}"
    elif table == "source_insight":
        ins = await SourceInsight.get(record_id)
        if not ins:
            raise NotFoundError(record_id)
        body = f"# Insight ({ins.insight_type})\n\n{ins.content}"
    else:
        raise InvalidInputError(f"Unsupported reference type: {table}")
    return PlainTextResponse(body[:200_000])  # type: ignore[return-value]


async def get_classroom_document(session_id: str) -> Dict[str, Any]:
    """Fetch the classroom JSON (stage + scenes) from OpenMAIC for native rendering."""
    session = await get_learning_session(session_id, refresh=False)
    if not session.classroom_id:
        raise NotFoundError("Classroom is not ready yet")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{openmaic_url()}/api/classroom", params={"id": session.classroom_id}, headers=_headers()
            )
    except httpx.HTTPError as e:
        raise ExternalServiceError(f"OpenMAIC unreachable: {e}") from e
    if r.status_code == 404:
        raise NotFoundError("Classroom not found in OpenMAIC (was its data folder cleared?)")
    if r.status_code >= 400:
        raise ExternalServiceError(f"OpenMAIC returned {r.status_code}: {r.text[:300]}")
    body = r.json()
    doc = body.get("classroom") or body.get("data", {}).get("classroom") or body
    # Absolute-ize media paths the sidecar serves (images, audio) so the browser can load them.
    public = public_openmaic_url()
    text = json.dumps(doc)
    text = text.replace('"/classroom-media/', f'"{public}/classroom-media/').replace(
        '"/api/classroom-media/', f'"{public}/api/classroom-media/'
    )
    return json.loads(text)


async def stream_classroom_chat(session_id: str, body: Dict[str, Any]):
    """Relay a classroom Q&A turn to OpenMAIC's stateless `/api/chat` (SSE) for the native player.

    The browser keeps the conversation; we add the classroom document (stage + scenes) as
    `storeState`, the default AI-teacher agent, and live retrieval from the session's notebooks
    as the agent's web-search backend. Yields raw SSE bytes.
    """
    session = await get_learning_session(session_id, refresh=False)
    doc = await get_classroom_document(session_id)
    scenes = doc.get("scenes") or []
    current = body.get("current_scene_id") or (scenes[0]["id"] if scenes else None)
    messages = body.get("messages") or []
    if not messages:
        raise InvalidInputError("messages is required")

    scope = (
        [str(n) for n in session.scope_notebooks]
        if session.scope_notebooks
        else ([session.notebook_id] if session.notebook_id else [])
    )
    # OpenMAIC's chat runtime has no search tool (its SearXNG hook is generation-only), so we
    # retrieve here: top notebook passages for the question ride along as context on the last
    # user message. The teacher is told to prefer them and cite by title.
    last = messages[-1]
    if isinstance(last, dict) and last.get("role") == "user":
        parts = last.get("parts") or []
        text_part = next((p for p in parts if isinstance(p, dict) and p.get("type") == "text" and p.get("text")), None)
        if text_part:
            question = str(text_part["text"])
            hits = await notebook_search_as_searxng(f"{question} {' '.join(scope_tag(n) for n in scope)}", limit=5)
            passages = [
                f"[{h['title']}]\n{h['content'][:1200]}" for h in hits.get("results", []) if h.get("content")
            ]
            if passages:
                text_part["text"] = (
                    f"{question}\n\n"
                    "<notebook_context>\n"
                    "Relevant passages retrieved from the learner's notebook (prefer these over guesses; "
                    "cite the bracketed title when you use one):\n\n" + "\n\n".join(passages) + "\n</notebook_context>"
                )

    payload: Dict[str, Any] = {
        "messages": messages,
        "storeState": {
            "stage": doc.get("stage"),
            "scenes": scenes,
            "currentSceneId": current,
            "mode": body.get("mode") or "classroom",
            "whiteboardOpen": False,
            **({"quizResults": body["quiz_results"]} if body.get("quiz_results") else {}),
        },
        "config": {"agentIds": ["default-1"], "sessionType": "qa", "piMaxAgentTurns": 1},
        "webSearchProviderId": "searxng",
    }
    if body.get("user_profile"):
        payload["userProfile"] = body["user_profile"]

    client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, read=600.0))
    try:
        async with client.stream(
            "POST", f"{openmaic_url()}/api/chat", json=payload, headers={**_headers(), "Accept": "text/event-stream"}
        ) as r:
            if r.status_code >= 400:
                text = (await r.aread()).decode(errors="replace")[:500]
                yield f'data: {json.dumps({"type": "error", "data": {"message": f"OpenMAIC {r.status_code}: {text}"}})}\n\n'.encode()
                return
            async for chunk in r.aiter_bytes():
                yield chunk
    except httpx.HTTPError as e:
        yield f'data: {json.dumps({"type": "error", "data": {"message": f"OpenMAIC unreachable: {e}"}})}\n\n'.encode()
    finally:
        await client.aclose()


REVIEW_INTERVALS_DAYS = [1, 3, 7, 14, 30]


def _next_review(score: Optional[float], reviews_done: int) -> datetime:
    """Simple spaced repetition: good scores stretch the interval, poor ones reset it."""
    idx = min(reviews_done, len(REVIEW_INTERVALS_DAYS) - 1)
    if score is not None and score < 0.6:
        idx = 0
    return datetime.now(timezone.utc) + timedelta(days=REVIEW_INTERVALS_DAYS[idx])


async def update_learning_progress(session_id: str, update: Dict[str, Any]) -> LearningSession:
    session = await get_learning_session(session_id, refresh=False)
    progress: Dict[str, Any] = dict(session.learner or {})
    now = datetime.now(timezone.utc)
    if update.get("scene_index") is not None:
        progress["scene_index"] = update["scene_index"]
    if update.get("step_index") is not None:
        progress["step_index"] = update["step_index"]
    if update.get("scenes_seen"):
        seen = set(progress.get("scenes_seen") or [])
        seen.update(update["scenes_seen"])
        progress["scenes_seen"] = sorted(seen)
    if update.get("quiz"):
        quizzes: Dict[str, Any] = dict(progress.get("quiz") or {})
        for scene_id, result in update["quiz"].items():
            quizzes[scene_id] = {**result, "at": now.isoformat()}
        progress["quiz"] = quizzes
        correct = sum(int(q.get("correct") or 0) for q in quizzes.values())
        total = sum(int(q.get("total") or 0) for q in quizzes.values())
        session.quiz_score = round(correct / total, 3) if total else None
    session.last_opened_at = now
    if update.get("completed") is True:
        reviews_done = int(progress.get("reviews_done") or 0)
        if session.completed_at:  # re-completing a classroom = a review pass
            reviews_done += 1
        progress["reviews_done"] = reviews_done
        session.completed_at = now
        session.review_due_at = _next_review(session.quiz_score, reviews_done)
    elif update.get("completed") is False:
        session.completed_at = None
        session.review_due_at = None
    session.learner = progress
    await session.save()
    return session
