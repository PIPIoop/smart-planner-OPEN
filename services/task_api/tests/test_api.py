from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

from services.task_api.app import create_app
from services.task_api.repository import SqliteTaskRepository


class TaskApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        database_path = Path(self._temporary_directory.name) / "tasks.sqlite3"
        app = create_app(SqliteTaskRepository(database_path))
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://task-api.test",
        )
        self.timestamp = datetime(
            2026, 8, 3, 10, tzinfo=timezone.utc
        ).isoformat()

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self._temporary_directory.cleanup()

    def _task_payload(self, task_id: str = "task-1") -> dict[str, object]:
        return {
            "id": task_id,
            "title": "Позвонить врачу",
            "note": "Создано тестом",
            "date": "2026-08-10",
            "startMinute": 1110,
            "priority": "normal",
            "isCompleted": False,
            "createdAt": self.timestamp,
            "updatedAt": self.timestamp,
        }

    async def test_health_reports_contract_version(self) -> None:
        response = await self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "schemaVersion": 2},
        )

    async def test_crud_lifecycle_uses_dart_json_contract(self) -> None:
        created = await self.client.post(
            "/api/v1/tasks", json=self._task_payload()
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["startMinute"], 1110)
        self.assertEqual(created.json()["durationMinutes"], 60)

        listed = await self.client.get("/api/v1/tasks")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

        updated_payload = self._task_payload()
        updated_payload["isCompleted"] = True
        updated_payload["completedAt"] = self.timestamp
        updated = await self.client.put(
            "/api/v1/tasks/task-1", json=updated_payload
        )
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.json()["isCompleted"])

        deleted = await self.client.delete("/api/v1/tasks/task-1")
        self.assertEqual(deleted.status_code, 204)
        listed_after_delete = await self.client.get("/api/v1/tasks")
        self.assertEqual(listed_after_delete.json(), [])

    async def test_persists_optional_deadline_fields(self) -> None:
        payload = self._task_payload("deadline-task")
        payload["deadlineDate"] = "2026-08-10"
        payload["deadlineMinute"] = 18 * 60
        payload["priority"] = "high"
        created = await self.client.post("/api/v1/tasks", json=payload)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["deadlineDate"], "2026-08-10")
        self.assertEqual(created.json()["deadlineMinute"], 1080)
        self.assertEqual(created.json()["priority"], "high")
        listed = (await self.client.get("/api/v1/tasks")).json()
        self.assertEqual(listed[0]["deadlineMinute"], 1080)


    async def test_create_is_idempotent_for_same_id_and_payload(self) -> None:
        first = await self.client.post(
            "/api/v1/tasks", json=self._task_payload()
        )
        second = await self.client.post(
            "/api/v1/tasks", json=self._task_payload()
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json(), second.json())
        listed = await self.client.get("/api/v1/tasks")
        self.assertEqual(len(listed.json()), 1)

    async def test_replace_all_is_atomic_and_rejects_duplicate_ids(self) -> None:
        payload = self._task_payload()
        response = await self.client.put(
            "/api/v1/tasks", json={"tasks": [payload, payload]}
        )
        self.assertEqual(response.status_code, 409)
        listed = await self.client.get("/api/v1/tasks")
        self.assertEqual(listed.json(), [])

    async def test_cors_allows_local_flutter_web_origin(self) -> None:
        response = await self.client.options(
            "/api/v1/tasks",
            headers={
                "Origin": "http://127.0.0.1:7357",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://127.0.0.1:7357",
        )

    async def test_goal_creation_is_atomic_and_generates_linked_tasks(self) -> None:
        goal = {
            "id": "goal-gym",
            "title": "Месяц ходить в зал",
            "note": "",
            "startDate": "2026-08-03",
            "endDate": "2026-08-09",
            "intervalDays": 2,
            "taskTitle": "Тренировка в зале",
            "taskNote": "",
            "taskStartMinute": 1080,
            "taskPriority": "high",
            "createdAt": self.timestamp,
            "updatedAt": self.timestamp,
        }
        tasks = []
        for index, task_date in enumerate(("2026-08-03", "2026-08-05", "2026-08-07", "2026-08-09")):
            task = self._task_payload(f"goal-gym-{index}")
            task.update({
                "title": "Тренировка в зале",
                "note": "",
                "date": task_date,
                "startMinute": 1080,
                "priority": "high",
                "goalId": "goal-gym",
                "goalOccurrenceDate": task_date,
            })
            tasks.append(task)

        response = await self.client.post(
            "/api/v1/goals", json={"goal": goal, "tasks": tasks}
        )
        self.assertEqual(response.status_code, 201)
        goals = await self.client.get("/api/v1/goals")
        listed_tasks = await self.client.get("/api/v1/tasks")
        self.assertEqual(len(goals.json()), 1)
        self.assertEqual(len(listed_tasks.json()), 4)
        self.assertTrue(all(task["goalId"] == "goal-gym" for task in listed_tasks.json()))

        deleted = await self.client.delete("/api/v1/goals/goal-gym")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual((await self.client.get("/api/v1/goals")).json(), [])
        self.assertEqual((await self.client.get("/api/v1/tasks")).json(), [])

    async def test_goal_rejects_schedule_gaps_atomically(self) -> None:
        goal = {
            "id": "goal-gap",
            "title": "Цель",
            "startDate": "2026-08-03",
            "endDate": "2026-08-07",
            "intervalDays": 2,
            "taskTitle": "Шаг",
            "createdAt": self.timestamp,
            "updatedAt": self.timestamp,
        }
        task = self._task_payload("gap-task")
        task.update({"title": "Шаг", "date": "2026-08-03", "goalId": "goal-gap", "goalOccurrenceDate": "2026-08-03"})
        response = await self.client.post(
            "/api/v1/goals", json={"goal": goal, "tasks": [task]}
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual((await self.client.get("/api/v1/goals")).json(), [])
        self.assertEqual((await self.client.get("/api/v1/tasks")).json(), [])
    async def test_goal_titles_cannot_be_only_whitespace(self) -> None:
        goal = {
            "id": "blank-goal",
            "title": "   ",
            "startDate": "2026-08-03",
            "endDate": "2026-08-03",
            "intervalDays": 1,
            "taskTitle": " \t ",
            "createdAt": self.timestamp,
            "updatedAt": self.timestamp,
        }
        task = self._task_payload("blank-goal-task")
        task.update({
            "title": "Шаг",
            "date": "2026-08-03",
            "goalId": "blank-goal",
            "goalOccurrenceDate": "2026-08-03",
        })
        response = await self.client.post(
            "/api/v1/goals", json={"goal": goal, "tasks": [task]}
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual((await self.client.get("/api/v1/goals")).json(), [])
        self.assertEqual((await self.client.get("/api/v1/tasks")).json(), [])
    async def test_group_crud_and_delete_unassigns_tasks(self) -> None:
        group = {
            "id": "group-work",
            "name": "Работа",
            "colorHex": "#3B82F6",
            "createdAt": self.timestamp,
            "updatedAt": self.timestamp,
        }
        created = await self.client.post("/api/v1/groups", json=group)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["colorHex"], "#3B82F6")
        duplicate_color = {**group, "id": "group-other", "name": "Другая"}
        self.assertEqual(
            (await self.client.post("/api/v1/groups", json=duplicate_color)).status_code,
            409,
        )

        task = self._task_payload("group-task")
        task["groupId"] = "group-work"
        self.assertEqual((await self.client.post("/api/v1/tasks", json=task)).status_code, 201)

        updated_group = {**group, "name": "Рабочие задачи", "colorHex": "#14B8A6"}
        updated = await self.client.put("/api/v1/groups/group-work", json=updated_group)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Рабочие задачи")

        deleted = await self.client.delete("/api/v1/groups/group-work")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual((await self.client.get("/api/v1/groups")).json(), [])
        tasks = (await self.client.get("/api/v1/tasks")).json()
        self.assertEqual(tasks[0]["groupId"], None)
    async def test_planner_data_round_trip_preserves_goal_template(self) -> None:
        group = {
            "id": "group-health",
            "name": "Здоровье",
            "colorHex": "#14B8A6",
            "createdAt": self.timestamp,
            "updatedAt": self.timestamp,
        }
        goal = {
            "id": "goal-gym",
            "title": "Ходить в зал",
            "note": "Месячная цель",
            "startDate": "2026-08-03",
            "endDate": "2026-08-05",
            "intervalDays": 2,
            "taskTitle": "Тренировка",
            "taskNote": "90 минут",
            "taskStartMinute": 600,
            "taskDurationMinutes": 90,
            "taskPriority": "high",
            "taskGroupId": "group-health",
            "createdAt": self.timestamp,
            "updatedAt": self.timestamp,
        }
        tasks = []
        for index, task_date in enumerate(("2026-08-03", "2026-08-05")):
            task = self._task_payload(f"gym-{index}")
            task.update({
                "title": "Тренировка",
                "note": "90 минут",
                "date": task_date,
                "startMinute": 600,
                "durationMinutes": 90,
                "priority": "high",
                "goalId": "goal-gym",
                "goalOccurrenceDate": task_date,
                "groupId": "group-health",
            })
            tasks.append(task)

        replaced = await self.client.put(
            "/api/v1/planner-data",
            json={"tasks": tasks, "goals": [goal], "groups": [group]},
        )
        self.assertEqual(replaced.status_code, 204, replaced.text)
        stored_goal = (await self.client.get("/api/v1/goals")).json()[0]
        self.assertEqual(stored_goal["taskDurationMinutes"], 90)
        self.assertEqual(stored_goal["taskGroupId"], "group-health")
        stored_tasks = (await self.client.get("/api/v1/tasks")).json()
        self.assertEqual([item["durationMinutes"] for item in stored_tasks], [90, 90])

        invalid = await self.client.put(
            "/api/v1/planner-data",
            json={
                "tasks": [{**tasks[0], "groupId": "missing"}],
                "goals": [],
                "groups": [],
            },
        )
        self.assertEqual(invalid.status_code, 409, invalid.text)
        self.assertEqual(len((await self.client.get("/api/v1/tasks")).json()), 2)
        self.assertEqual(len((await self.client.get("/api/v1/goals")).json()), 1)
        self.assertEqual(len((await self.client.get("/api/v1/groups")).json()), 1)

    async def test_existing_goal_database_migrates_task_duration(self) -> None:
        legacy_directory = tempfile.TemporaryDirectory()
        try:
            path = Path(legacy_directory.name) / "legacy-goal.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute("""CREATE TABLE goals (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, note TEXT NOT NULL,
                    start_date TEXT NOT NULL, end_date TEXT NOT NULL,
                    interval_days INTEGER NOT NULL, task_title TEXT NOT NULL,
                    task_note TEXT NOT NULL, task_start_minute INTEGER,
                    task_priority TEXT NOT NULL, task_group_id TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )""")
                connection.execute(
                    "INSERT INTO goals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "legacy-goal", "Старая цель", "", "2026-08-03",
                        "2026-08-03", 1, "Шаг", "", 600, "normal", None,
                        self.timestamp, self.timestamp,
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            migrated = SqliteTaskRepository(path).list_goals()
            self.assertEqual(migrated[0].task_duration_minutes, 60)
        finally:
            legacy_directory.cleanup()

    async def test_legacy_completed_task_receives_completion_timestamp(self) -> None:
        legacy_directory = tempfile.TemporaryDirectory()
        try:
            path = Path(legacy_directory.name) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute("""
                    CREATE TABLE tasks (
                        id TEXT PRIMARY KEY, title TEXT NOT NULL, note TEXT NOT NULL,
                        task_date TEXT NOT NULL, start_minute INTEGER, priority TEXT NOT NULL,
                        is_completed INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                    )
                """)
                connection.execute(
                    "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("legacy", "Старая задача", "", "2026-08-03", None, "normal", 1, self.timestamp, self.timestamp),
                )
                connection.commit()
            finally:
                connection.close()
            migrated = SqliteTaskRepository(path).list_all()
            self.assertTrue(migrated[0].is_completed)
            self.assertEqual(migrated[0].completed_at, migrated[0].updated_at)
        finally:
            legacy_directory.cleanup()

if __name__ == "__main__":
    unittest.main()