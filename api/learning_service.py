"""
Learn feature service: turn a notebook into an interactive OpenMAIC classroom.

OpenMAIC (vendor/openmaic) runs as a sidecar Next.js service (OPENMAIC_URL,
default http://localhost:3100). We bundle the notebook's sources, insights and
notes into a text corpus, submit it to OpenMAIC's `POST /api/generate-classroom`
job API, and track the job on a `learning_session` record.
"""

import asyncio
import os
from typing import Any, Dict, List, Optional

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
) -> LearningSession:
    notebook = await Notebook.get(notebook_id)
    if not notebook:
        raise NotFoundError(f"Notebook {notebook_id} not found")

    bundle = await build_material_bundle(
        notebook, include_sources, include_insights, include_notes
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
        },
        material_stats=bundle["stats"],
    )
    await session.save()

    payload = {
        "requirement": requirement,
        "pdfContent": {"text": bundle["text"], "images": []},
        "enableTTS": enable_tts,
        "enableImageGeneration": enable_image_generation,
        "enableVideoGeneration": False,
        "enableWebSearch": enable_web_search,
    }
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
