from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .models import GoalCreationRequest, GoalRecord, TaskCreateRequest, TaskGroupRecord, TaskRecord
from .repository import TaskConflictError, TaskRepository


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository

    def list_tasks(self) -> list[TaskRecord]:
        return self._repository.list_all()

    def create_task(self, request: TaskCreateRequest) -> TaskRecord:
        if request.id is not None:
            existing = self._repository.get(request.id)
            if existing is not None:
                if self._same_creation(existing, request):
                    return existing
                raise TaskConflictError(f"Task with ID {request.id!r} already exists")
        now = datetime.now(timezone.utc)
        created_at = request.created_at or now
        updated_at = request.updated_at or created_at
        task = TaskRecord(
            id=request.id or uuid4().hex, title=request.title, note=request.note,
            date=request.date, start_minute=request.start_minute, duration_minutes=request.duration_minutes,
            deadline_date=request.deadline_date, deadline_minute=request.deadline_minute, priority=request.priority,
            is_completed=request.is_completed, goal_id=request.goal_id,
            goal_occurrence_date=request.goal_occurrence_date, completed_at=request.completed_at, group_id=request.group_id, created_at=created_at, updated_at=updated_at,
        )
        return self._repository.create(task)

    def update_task(self, task: TaskRecord) -> TaskRecord:
        return self._repository.update(task)

    def delete_task(self, task_id: str) -> None:
        self._repository.delete(task_id)

    def replace_all(self, tasks: list[TaskRecord]) -> None:
        self._repository.replace_all(tasks)

    def replace_planner_data(
        self,
        tasks: list[TaskRecord],
        goals: list[GoalRecord],
        groups: list[TaskGroupRecord],
    ) -> None:
        self._repository.replace_planner_data(tasks, goals, groups)

    def list_goals(self) -> list[GoalRecord]:
        return self._repository.list_goals()

    def create_goal(self, request: GoalCreationRequest) -> GoalCreationRequest:
        expected_dates = []
        current = request.goal.start_date
        while current <= request.goal.end_date:
            expected_dates.append(current)
            current += timedelta(days=request.goal.interval_days)
        actual_dates = [task.date for task in request.tasks]
        if actual_dates != expected_dates:
            raise ValueError("Generated task dates do not match the goal schedule")
        if any(
            task.goal_id != request.goal.id
            or task.goal_occurrence_date != expected_date
            or task.title != request.goal.task_title
            or task.note != request.goal.task_note
            or task.start_minute != request.goal.task_start_minute
            or task.priority != request.goal.task_priority
            or task.duration_minutes != request.goal.task_duration_minutes
            or task.group_id != request.goal.task_group_id
            or task.is_completed
            for task, expected_date in zip(request.tasks, expected_dates)
        ):
            raise ValueError("Generated tasks do not match the goal template")
        self._repository.create_goal(request.goal, request.tasks)
        return request

    def delete_goal(self, goal_id: str) -> None:
        self._repository.delete_goal(goal_id)

    def list_groups(self) -> list[TaskGroupRecord]:
        return self._repository.list_groups()

    def create_group(self, group: TaskGroupRecord) -> TaskGroupRecord:
        return self._repository.create_group(group)

    def update_group(self, group: TaskGroupRecord) -> TaskGroupRecord:
        return self._repository.update_group(group)

    def delete_group(self, group_id: str) -> None:
        self._repository.delete_group(group_id)
    @staticmethod
    def _same_creation(existing: TaskRecord, request: TaskCreateRequest) -> bool:
        return (
            existing.title == request.title and existing.note == request.note
            and existing.date == request.date and existing.start_minute == request.start_minute
            and existing.duration_minutes == request.duration_minutes
            and existing.deadline_date == request.deadline_date and existing.deadline_minute == request.deadline_minute
            and existing.priority == request.priority and existing.is_completed == request.is_completed
            and existing.goal_id == request.goal_id
            and existing.goal_occurrence_date == request.goal_occurrence_date
            and existing.completed_at == request.completed_at
            and existing.group_id == request.group_id
            and (request.created_at is None or existing.created_at == request.created_at)
            and (request.updated_at is None or existing.updated_at == request.updated_at)
        )