import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from app.models.enums import TaskPriority, TaskStatus
from app.schemas.common import StrictModel, Timestamped

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(max_length=5000)]
Estimate = Annotated[int, Field(gt=0, le=100_000)]


class TaskCreate(StrictModel):
    project_id: uuid.UUID
    title: Title
    description: Description | None = None
    status: TaskStatus = TaskStatus.todo
    priority: TaskPriority = TaskPriority.medium
    due_date: date | None = None
    estimate_minutes: Estimate | None = None


class TaskUpdate(StrictModel):
    """project_id is intentionally absent: tasks cannot move between projects (extra fields → 422)."""

    title: Title | None = None
    description: Description | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: date | None = None
    estimate_minutes: Estimate | None = None

    @model_validator(mode="after")
    def _non_nullable(self) -> "TaskUpdate":
        for field in ("title", "status", "priority"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class TaskReorder(StrictModel):
    project_id: uuid.UUID
    ordered_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=1000)]


class TaskOut(Timestamped):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None
    estimate_minutes: int | None
    position: int
    completed_at: datetime | None
