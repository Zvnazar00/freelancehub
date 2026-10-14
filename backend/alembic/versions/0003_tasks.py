"""Tasks.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

task_status = postgresql.ENUM("todo", "in_progress", "done", name="task_status", create_type=False)
task_priority = postgresql.ENUM("low", "medium", "high", name="task_priority", create_type=False)


def upgrade() -> None:
    task_status.create(op.get_bind(), checkfirst=True)
    task_priority.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", task_status, nullable=False, server_default="todo"),
        sa.Column("priority", task_priority, nullable=False, server_default="medium"),
        sa.Column("due_date", sa.Date()),
        sa.Column("estimate_minutes", sa.Integer()),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
        sa.UniqueConstraint("id", "user_id", name="uq_tasks_id_user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_tasks_user_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "user_id"],
            ["projects.id", "projects.user_id"],
            name="fk_tasks_project_owner",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("estimate_minutes IS NULL OR estimate_minutes > 0", name="ck_tasks_estimate_positive"),
        sa.CheckConstraint(
            "(status = 'done') = (completed_at IS NOT NULL)", name="ck_tasks_completed_at_matches_status"
        ),
    )
    op.create_index("ix_tasks_project_status_position", "tasks", ["project_id", "status", "position"])
    op.create_index("ix_tasks_user_due", "tasks", ["user_id", "due_date"], postgresql_where=sa.text("status <> 'done'"))


def downgrade() -> None:
    op.drop_index("ix_tasks_user_due", table_name="tasks")
    op.drop_index("ix_tasks_project_status_position", table_name="tasks")
    op.drop_table("tasks")
    task_priority.drop(op.get_bind(), checkfirst=True)
    task_status.drop(op.get_bind(), checkfirst=True)
