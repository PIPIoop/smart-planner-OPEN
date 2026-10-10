from __future__ import annotations

import sqlite3
from datetime import timedelta
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .models import GoalRecord, TaskGroupRecord, TaskPriority, TaskRecord


class TaskNotFoundError(LookupError):
    pass


class GoalNotFoundError(LookupError):
    pass


class TaskConflictError(RuntimeError):
    pass


class TaskRepository(ABC):
    @abstractmethod
    def list_all(self) -> list[TaskRecord]: raise NotImplementedError
    @abstractmethod
    def get(self, task_id: str) -> TaskRecord | None: raise NotImplementedError
    @abstractmethod
    def create(self, task: TaskRecord) -> TaskRecord: raise NotImplementedError
    @abstractmethod
    def update(self, task: TaskRecord) -> TaskRecord: raise NotImplementedError
    @abstractmethod
    def delete(self, task_id: str) -> None: raise NotImplementedError
    @abstractmethod
    def replace_all(self, tasks: list[TaskRecord]) -> None: raise NotImplementedError
    @abstractmethod
    def replace_generated_tasks(
        self,
        *,
        id_prefix: str,
        note_marker: str,
        tasks: list[TaskRecord],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def replace_planner_data(
        self,
        tasks: list[TaskRecord],
        goals: list[GoalRecord],
        groups: list[TaskGroupRecord],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_goals(self) -> list[GoalRecord]: raise NotImplementedError
    @abstractmethod
    def create_goal(self, goal: GoalRecord, tasks: list[TaskRecord]) -> None: raise NotImplementedError
    @abstractmethod
    def delete_goal(self, goal_id: str) -> None: raise NotImplementedError
    @abstractmethod
    def list_groups(self) -> list[TaskGroupRecord]: raise NotImplementedError
    @abstractmethod
    def create_group(self, group: TaskGroupRecord) -> TaskGroupRecord: raise NotImplementedError
    @abstractmethod
    def update_group(self, group: TaskGroupRecord) -> TaskGroupRecord: raise NotImplementedError
    @abstractmethod
    def delete_group(self, group_id: str) -> None: raise NotImplementedError


class SqliteTaskRepository(TaskRepository):
    @property
    def database_path(self) -> Path:
        return self._database_path

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path.resolve()
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path, timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS task_groups (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    color_hex TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    note TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    interval_days INTEGER NOT NULL,
                    task_title TEXT NOT NULL,
                    task_note TEXT NOT NULL,
                    task_start_minute INTEGER,
                    task_duration_minutes INTEGER,
                    task_priority TEXT NOT NULL,
                    task_group_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (interval_days BETWEEN 1 AND 365),
                    CHECK (task_start_minute IS NULL OR task_start_minute BETWEEN 0 AND 1439),
                    CHECK (task_priority IN ('low', 'normal', 'high'))
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    note TEXT NOT NULL,
                    task_date TEXT NOT NULL,
                    start_minute INTEGER,
                    duration_minutes INTEGER,
                    deadline_date TEXT,
                    deadline_minute INTEGER,
                    priority TEXT NOT NULL,
                    is_completed INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    goal_id TEXT,
                    goal_occurrence_date TEXT,
                    completed_at TEXT,
                    group_id TEXT,
                    CHECK (start_minute IS NULL OR start_minute BETWEEN 0 AND 1439),
                    CHECK (deadline_minute IS NULL OR deadline_minute BETWEEN 0 AND 1439),
                    CHECK (priority IN ('low', 'normal', 'high')),
                    CHECK (is_completed IN (0, 1))
                )
            """)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if "duration_minutes" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN duration_minutes INTEGER")
            connection.execute("UPDATE tasks SET duration_minutes = 60 WHERE start_minute IS NOT NULL AND duration_minutes IS NULL")
            if "deadline_date" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN deadline_date TEXT")
            if "deadline_minute" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN deadline_minute INTEGER")
            if "goal_id" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN goal_id TEXT")
            if "goal_occurrence_date" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN goal_occurrence_date TEXT")
            if "completed_at" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")
            if "group_id" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN group_id TEXT")
            goal_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(goals)").fetchall()
            }
            if "task_group_id" not in goal_columns:
                connection.execute("ALTER TABLE goals ADD COLUMN task_group_id TEXT")
            if "task_duration_minutes" not in goal_columns:
                connection.execute("ALTER TABLE goals ADD COLUMN task_duration_minutes INTEGER")
            connection.execute(
                "UPDATE goals SET task_duration_minutes = 60 "
                "WHERE task_start_minute IS NOT NULL AND task_duration_minutes IS NULL"
            )
            connection.execute(
                "UPDATE tasks SET completed_at = updated_at "
                "WHERE is_completed = 1 AND completed_at IS NULL"
            )
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_task_groups_color ON task_groups(color_hex)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_tasks_date_time ON tasks(task_date, start_minute, created_at)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_tasks_goal ON tasks(goal_id, task_date)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_tasks_group ON tasks(group_id, task_date)")

    def list_all(self) -> list[TaskRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM tasks ORDER BY task_date, start_minute IS NULL, start_minute, created_at").fetchall()
        return [self._row_to_task(row) for row in rows]

    def get(self, task_id: str) -> TaskRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return None if row is None else self._row_to_task(row)

    def create(self, task: TaskRecord) -> TaskRecord:
        try:
            with self._connect() as connection:
                connection.execute(self._task_insert_sql(), self._task_parameters(task))
        except sqlite3.IntegrityError as error:
            raise TaskConflictError(f"Task with ID {task.id!r} already exists") from error
        return task

    def update(self, task: TaskRecord) -> TaskRecord:
        with self._connect() as connection:
            cursor = connection.execute("""
                UPDATE tasks SET title=?, note=?, task_date=?, start_minute=?, priority=?,
                    duration_minutes=?, deadline_date=?, deadline_minute=?, is_completed=?, created_at=?, updated_at=?, goal_id=?, goal_occurrence_date=?, completed_at=?, group_id=?
                WHERE id=?
            """, (
                task.title, task.note, task.date.isoformat(), task.start_minute,
                task.priority.value, task.duration_minutes,
                task.deadline_date.isoformat() if task.deadline_date else None, task.deadline_minute,
                int(task.is_completed), task.created_at.isoformat(),
                task.updated_at.isoformat(), task.goal_id,
                task.goal_occurrence_date.isoformat() if task.goal_occurrence_date else None,
                task.completed_at.isoformat() if task.completed_at else None, task.group_id, task.id,
            ))
            if cursor.rowcount != 1:
                raise TaskNotFoundError(task.id)
        return task

    def delete(self, task_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            if cursor.rowcount != 1:
                raise TaskNotFoundError(task_id)

    def replace_all(self, tasks: list[TaskRecord]) -> None:
        ids = [task.id for task in tasks]
        if len(ids) != len(set(ids)):
            raise TaskConflictError("Replacement contains duplicate task IDs")
        with self._connect() as connection:
            connection.execute("DELETE FROM tasks")
            connection.executemany(self._task_insert_sql(), [self._task_parameters(task) for task in tasks])

    def replace_generated_tasks(
        self,
        *,
        id_prefix: str,
        note_marker: str,
        tasks: list[TaskRecord],
    ) -> None:
        ids = [task.id for task in tasks]
        if len(ids) != len(set(ids)):
            raise TaskConflictError("Generated replacement contains duplicate task IDs")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = connection.execute(
                    f"SELECT id, note FROM tasks WHERE id IN ({placeholders})",
                    ids,
                ).fetchall()
                for row in rows:
                    belongs_to_replacement = (
                        str(row["id"]).startswith(id_prefix)
                        and note_marker in str(row["note"])
                    )
                    if not belongs_to_replacement:
                        raise TaskConflictError(
                            f"Calendar task with ID {row['id']!r} already exists"
                        )
            connection.execute(
                """DELETE FROM tasks
                   WHERE substr(id, 1, length(?))=? AND instr(note, ?) > 0""",
                (id_prefix, id_prefix, note_marker),
            )
            if tasks:
                connection.executemany(
                    self._task_insert_sql(),
                    [self._task_parameters(task) for task in tasks],
                )

    def replace_planner_data(
        self,
        tasks: list[TaskRecord],
        goals: list[GoalRecord],
        groups: list[TaskGroupRecord],
    ) -> None:
        self._validate_planner_data(tasks, goals, groups)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DELETE FROM tasks")
                connection.execute("DELETE FROM goals")
                connection.execute("DELETE FROM task_groups")
                if groups:
                    connection.executemany(
                        "INSERT INTO task_groups (id, name, color_hex, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                        [self._group_parameters(group) for group in groups],
                    )
                if goals:
                    connection.executemany(
                        """INSERT INTO goals (
                            id, title, note, start_date, end_date, interval_days,
                            task_title, task_note, task_start_minute,
                            task_duration_minutes, task_priority, task_group_id,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        [self._goal_parameters(goal) for goal in goals],
                    )
                if tasks:
                    connection.executemany(
                        self._task_insert_sql(),
                        [self._task_parameters(task) for task in tasks],
                    )
        except sqlite3.IntegrityError as error:
            raise TaskConflictError(
                "Planner data violates a database constraint"
            ) from error

    @staticmethod
    def _validate_planner_data(
        tasks: list[TaskRecord],
        goals: list[GoalRecord],
        groups: list[TaskGroupRecord],
    ) -> None:
        task_ids = [task.id for task in tasks]
        goal_ids = [goal.id for goal in goals]
        group_ids = [group.id for group in groups]
        colors = [group.color_hex for group in groups]
        if len(task_ids) != len(set(task_ids)):
            raise TaskConflictError("Planner data contains duplicate task IDs")
        if len(goal_ids) != len(set(goal_ids)):
            raise TaskConflictError("Planner data contains duplicate goal IDs")
        if len(group_ids) != len(set(group_ids)):
            raise TaskConflictError("Planner data contains duplicate group IDs")
        if len(colors) != len(set(colors)):
            raise TaskConflictError("Planner data contains duplicate group colors")
        known_goals = set(goal_ids)
        known_groups = set(group_ids)
        if any(task.goal_id is not None and task.goal_id not in known_goals for task in tasks):
            raise TaskConflictError("Planner task references an unknown goal")
        if any(task.group_id is not None and task.group_id not in known_groups for task in tasks):
            raise TaskConflictError("Planner task references an unknown group")
        if any(goal.task_group_id is not None and goal.task_group_id not in known_groups for goal in goals):
            raise TaskConflictError("Planner goal references an unknown group")
        for goal in goals:
            expected_dates = set()
            current = goal.start_date
            while current <= goal.end_date:
                expected_dates.add(current)
                current += timedelta(days=goal.interval_days)
            actual = [
                task.goal_occurrence_date
                for task in tasks
                if task.goal_id == goal.id
            ]
            if len(actual) != len(set(actual)):
                raise TaskConflictError(
                    f"Planner goal {goal.id!r} contains duplicate occurrences"
                )
            if any(occurrence not in expected_dates for occurrence in actual):
                raise TaskConflictError(
                    f"Planner goal {goal.id!r} contains an invalid occurrence date"
                )

    def list_goals(self) -> list[GoalRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM goals ORDER BY start_date, created_at").fetchall()
        return [self._row_to_goal(row) for row in rows]

    def create_goal(self, goal: GoalRecord, tasks: list[TaskRecord]) -> None:
        try:
            with self._connect() as connection:
                connection.execute("""
                    INSERT INTO goals (
                        id, title, note, start_date, end_date, interval_days,
                        task_title, task_note, task_start_minute, task_duration_minutes, task_priority,
                        task_group_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, self._goal_parameters(goal))
                connection.executemany(self._task_insert_sql(), [self._task_parameters(task) for task in tasks])
        except sqlite3.IntegrityError as error:
            raise TaskConflictError(f"Goal or generated task already exists: {goal.id}") from error

    def delete_goal(self, goal_id: str) -> None:
        with self._connect() as connection:
            exists = connection.execute("SELECT 1 FROM goals WHERE id=?", (goal_id,)).fetchone()
            if exists is None:
                raise GoalNotFoundError(goal_id)
            connection.execute("DELETE FROM tasks WHERE goal_id=?", (goal_id,))
            connection.execute("DELETE FROM goals WHERE id=?", (goal_id,))

    def list_groups(self) -> list[TaskGroupRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM task_groups ORDER BY name COLLATE NOCASE").fetchall()
        return [self._row_to_group(row) for row in rows]

    def create_group(self, group: TaskGroupRecord) -> TaskGroupRecord:
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO task_groups (id, name, color_hex, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    self._group_parameters(group),
                )
        except sqlite3.IntegrityError as error:
            raise TaskConflictError(f"Group with ID {group.id!r} already exists") from error
        return group

    def update_group(self, group: TaskGroupRecord) -> TaskGroupRecord:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE task_groups SET name=?, color_hex=?, created_at=?, updated_at=? WHERE id=?",
                (group.name, group.color_hex, group.created_at.isoformat(), group.updated_at.isoformat(), group.id),
            )
            if cursor.rowcount != 1:
                raise GoalNotFoundError(group.id)
        return group

    def delete_group(self, group_id: str) -> None:
        with self._connect() as connection:
            exists = connection.execute("SELECT 1 FROM task_groups WHERE id=?", (group_id,)).fetchone()
            if exists is None:
                raise GoalNotFoundError(group_id)
            connection.execute("UPDATE tasks SET group_id=NULL WHERE group_id=?", (group_id,))
            connection.execute("UPDATE goals SET task_group_id=NULL WHERE task_group_id=?", (group_id,))
            connection.execute("DELETE FROM task_groups WHERE id=?", (group_id,))
    @staticmethod
    def _task_insert_sql() -> str:
        return """
            INSERT INTO tasks (
                id, title, note, task_date, start_minute, priority, duration_minutes, deadline_date, deadline_minute, is_completed,
                created_at, updated_at, goal_id, goal_occurrence_date, completed_at, group_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

    @staticmethod
    def _task_parameters(task: TaskRecord) -> tuple[object, ...]:
        return (
            task.id, task.title, task.note, task.date.isoformat(), task.start_minute,
            task.priority.value, task.duration_minutes,
            task.deadline_date.isoformat() if task.deadline_date else None, task.deadline_minute,
            int(task.is_completed), task.created_at.isoformat(),
            task.updated_at.isoformat(), task.goal_id,
            task.goal_occurrence_date.isoformat() if task.goal_occurrence_date else None,
            task.completed_at.isoformat() if task.completed_at else None, task.group_id,
        )

    @staticmethod
    def _goal_parameters(goal: GoalRecord) -> tuple[object, ...]:
        return (
            goal.id, goal.title, goal.note, goal.start_date.isoformat(), goal.end_date.isoformat(),
            goal.interval_days, goal.task_title, goal.task_note, goal.task_start_minute,
            goal.task_duration_minutes, goal.task_priority.value, goal.task_group_id,
            goal.created_at.isoformat(), goal.updated_at.isoformat(),
        )

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            id=row["id"], title=row["title"], note=row["note"], date=row["task_date"],
            start_minute=row["start_minute"], duration_minutes=row["duration_minutes"],
            deadline_date=row["deadline_date"], deadline_minute=row["deadline_minute"],
            priority=TaskPriority(row["priority"]),
            is_completed=bool(row["is_completed"]), created_at=row["created_at"],
            updated_at=row["updated_at"], goal_id=row["goal_id"],
            goal_occurrence_date=row["goal_occurrence_date"], completed_at=row["completed_at"], group_id=row["group_id"],
        )

    @staticmethod
    def _row_to_goal(row: sqlite3.Row) -> GoalRecord:
        return GoalRecord(
            id=row["id"], title=row["title"], note=row["note"], start_date=row["start_date"],
            end_date=row["end_date"], interval_days=row["interval_days"], task_title=row["task_title"],
            task_note=row["task_note"], task_start_minute=row["task_start_minute"],
            task_duration_minutes=row["task_duration_minutes"],
            task_priority=TaskPriority(row["task_priority"]), task_group_id=row["task_group_id"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _group_parameters(group: TaskGroupRecord) -> tuple[object, ...]:
        return (group.id, group.name, group.color_hex, group.created_at.isoformat(), group.updated_at.isoformat())

    @staticmethod
    def _row_to_group(row: sqlite3.Row) -> TaskGroupRecord:
        return TaskGroupRecord(
            id=row["id"], name=row["name"], color_hex=row["color_hex"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
