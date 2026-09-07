"""Learning sessions: a classroom generated from a notebook by the OpenMAIC sidecar."""

from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional, Union

from pydantic import Field, field_validator
from surrealdb import RecordID

from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.base import ObjectModel


class LearningSession(ObjectModel):
    table_name: ClassVar[str] = "learning_session"

    notebook: Union[str, RecordID]
    title: str
    requirement: str
    status: str = "pending"  # pending | running | succeeded | failed
    step: Optional[str] = None
    progress: Optional[int] = None
    message: Optional[str] = None
    error: Optional[str] = None
    job_id: Optional[str] = None
    classroom_id: Optional[str] = None
    classroom_url: Optional[str] = None
    options: Optional[Dict[str, Any]] = Field(default_factory=dict)
    material_stats: Optional[Dict[str, Any]] = Field(default_factory=dict)
    # learner state (migration 26)
    learner: Optional[Dict[str, Any]] = Field(default_factory=dict)
    completed_at: Optional[datetime] = None
    last_opened_at: Optional[datetime] = None
    quiz_score: Optional[float] = None
    review_due_at: Optional[datetime] = None

    @field_validator("notebook", mode="before")
    @classmethod
    def _notebook_as_record(cls, v):
        if isinstance(v, str):
            return ensure_record_id(v)
        return v

    @property
    def notebook_id(self) -> str:
        return str(self.notebook)

    def _prepare_save_data(self) -> Dict[str, Any]:
        """model_dump() stringifies RecordIDs; SurrealDB needs a real record link."""
        data = super()._prepare_save_data()
        if data.get("notebook") is not None:
            data["notebook"] = ensure_record_id(data["notebook"])
        return data

    @classmethod
    async def all_recent(cls, limit: int = 100) -> List["LearningSession"]:
        rows = await repo_query(
            "SELECT * FROM learning_session ORDER BY created DESC LIMIT $limit", {"limit": limit}
        )
        return [cls(**row) for row in rows] if rows else []

    @classmethod
    async def for_notebook(cls, notebook_id: str) -> List["LearningSession"]:
        rows = await repo_query(
            "SELECT * FROM learning_session WHERE notebook = $nb ORDER BY created DESC",
            {"nb": ensure_record_id(notebook_id)},
        )
        return [cls(**row) for row in rows] if rows else []
