"""Learn feature: generate interactive OpenMAIC classrooms from a notebook."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from api import learning_service
from api.models import (
    LearningFromQuestionCreate,
    LearningProgressUpdate,
    LearningSessionCreate,
    LearningSessionResponse,
    LearningStatusResponse,
)
from open_notebook.domain.learning import LearningSession

router = APIRouter()


def _to_response(s: LearningSession, notebook_name: Optional[str] = None) -> LearningSessionResponse:
    return LearningSessionResponse(
        id=str(s.id),
        notebook_id=s.notebook_id,
        notebook_name=notebook_name,
        question=s.question,
        scope_notebooks=[str(n) for n in s.scope_notebooks] if s.scope_notebooks else None,
        title=s.title,
        requirement=s.requirement,
        status=s.status,
        step=s.step,
        progress=s.progress,
        message=s.message,
        error=s.error,
        job_id=s.job_id,
        classroom_id=s.classroom_id,
        classroom_url=s.classroom_url,
        options=s.options,
        material_stats=s.material_stats,
        learner=s.learner,
        completed_at=str(s.completed_at) if s.completed_at else None,
        last_opened_at=str(s.last_opened_at) if s.last_opened_at else None,
        quiz_score=s.quiz_score,
        review_due_at=str(s.review_due_at) if s.review_due_at else None,
        created=str(s.created) if s.created else None,
        updated=str(s.updated) if s.updated else None,
    )


@router.get("/learn/status", response_model=LearningStatusResponse)
async def learn_status():
    """Whether the OpenMAIC sidecar is reachable."""
    return LearningStatusResponse(**await learning_service.openmaic_health())


@router.get("/learn", response_model=List[LearningSessionResponse])
async def list_all_sessions(refresh: bool = Query(True, description="Poll running jobs")):
    """All classrooms across notebooks, newest first."""
    sessions = await learning_service.list_all_learning_sessions(refresh=refresh)
    names = await learning_service.notebook_names({s.notebook_id for s in sessions})
    return [_to_response(s, names.get(s.notebook_id)) for s in sessions]


@router.post("/learn/from-question", response_model=LearningSessionResponse, status_code=202)
async def create_from_question(body: LearningFromQuestionCreate):
    """'Learn' on Ask & Search: a classroom that answers a question from the selected notebooks
    (or the whole knowledge base when no scope is given)."""
    from api.routers.search import resolve_notebook_scope

    notebook_ids = await resolve_notebook_scope(body.scope_notebook_ids)
    session = await learning_service.create_learning_session_from_question(
        body.question, notebook_ids=notebook_ids, title=body.title, enable_tts=body.enable_tts
    )
    return _to_response(session)


@router.get(
    "/notebooks/{notebook_id}/learn", response_model=List[LearningSessionResponse]
)
async def list_sessions(
    notebook_id: str, refresh: bool = Query(True, description="Poll running jobs")
):
    sessions = await learning_service.list_learning_sessions(notebook_id, refresh=refresh)
    return [_to_response(s) for s in sessions]


@router.post(
    "/notebooks/{notebook_id}/learn", response_model=LearningSessionResponse, status_code=202
)
async def create_session(notebook_id: str, body: LearningSessionCreate):
    session = await learning_service.create_learning_session(
        notebook_id,
        requirement=body.requirement,
        title=body.title,
        include_sources=body.include_sources,
        include_insights=body.include_insights,
        include_notes=body.include_notes,
        enable_tts=body.enable_tts,
        enable_image_generation=body.enable_image_generation,
        enable_web_search=body.enable_web_search,
        live_retrieval=body.live_retrieval,
    )
    return _to_response(session)


@router.get("/learn/searxng/search")
async def notebook_search_searxng(
    q: str = Query("", description="Search query; may carry a [nb:<notebook id>] scope tag"),
    format: str = Query("json"),  # noqa: A002 - SearXNG parameter name
    limit: int = Query(8, ge=1, le=25),
    notebook_id: Optional[str] = Query(None),
):
    """SearXNG-compatible search over the knowledge base, consumed by the OpenMAIC sidecar as
    its 'web search' backend so classrooms can pull from notebooks live."""
    return await learning_service.notebook_search_as_searxng(q, limit, notebook_id)


@router.get("/learn/ref/{record_id}")
async def learn_reference(record_id: str):
    """Resolve a search hit (source / note / insight) to its text — the URL OpenMAIC may fetch."""
    return await learning_service.learn_reference(record_id)


@router.get("/learn/{session_id}/classroom")
async def get_classroom(session_id: str):
    """Classroom document (stage + scenes) for the in-app renderer."""
    return await learning_service.get_classroom_document(session_id)


@router.post("/learn/{session_id}/chat")
async def classroom_chat(session_id: str, body: Dict[str, Any]):
    """Ask the AI teacher (SSE). Body: {messages: UIMessage[], current_scene_id?, quiz_results?}.
    Relays OpenMAIC's stateless chat with the classroom as context and notebook-scoped retrieval."""
    return StreamingResponse(
        learning_service.stream_classroom_chat(session_id, body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.patch("/learn/{session_id}/progress", response_model=LearningSessionResponse)
async def update_progress(session_id: str, body: LearningProgressUpdate):
    """Learner state from the native player: position, scenes seen, quiz results, completion."""
    session = await learning_service.update_learning_progress(session_id, body.model_dump(exclude_none=True))
    return _to_response(session)


@router.get("/learn/{session_id}", response_model=LearningSessionResponse)
async def get_session(session_id: str):
    return _to_response(await learning_service.get_learning_session(session_id))


@router.delete("/learn/{session_id}", status_code=204)
async def delete_session(session_id: str):
    await learning_service.delete_learning_session(session_id)
    return None
