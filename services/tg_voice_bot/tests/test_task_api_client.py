from __future__ import annotations

import json
import sys
import unittest
from datetime import date, time
from pathlib import Path

import httpx

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from task_api_client import TaskApiClient, TaskApiError, TaskApiSubscriptionError
from task_extractor import TaskExtraction


class TaskApiClientTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.extraction = TaskExtraction(
            intent="create_task",
            source_text="Завтра в 18:30 тренировка",
            title="Тренировка",
            scheduled_date=date(2026, 8, 4),
            scheduled_time=time(18, 30),
            confidence=1.0,
        )

    async def test_maps_extraction_to_shared_contract(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            payload = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    **payload,
                    "createdAt": "2026-08-03T10:00:00Z",
                    "updatedAt": "2026-08-03T10:00:00Z",
                },
            )

        client = TaskApiClient(
            base_url="http://task-api.test/",
            transport=httpx.MockTransport(handler),
        )
        first = await client.create_task(
            extraction=self.extraction,
            user_id=7,
            chat_id=11,
            confirmation_token="same-token",
        )
        second = await client.create_task(
            extraction=self.extraction,
            user_id=7,
            chat_id=11,
            confirmation_token="same-token",
        )

        self.assertEqual(requests[0].url.path, "/api/v1/tasks")
        payload = json.loads(requests[0].content)
        self.assertEqual(payload["startMinute"], 1110)
        self.assertEqual(payload["durationMinutes"], 60)
        self.assertEqual(payload["priority"], "normal")
        self.assertIn("Исходный текст", payload["note"])
        self.assertEqual(first["id"], second["id"])

    async def test_maps_extracted_range_duration(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(201, json=captured)

        extraction = TaskExtraction(
            intent="create_task",
            source_text="Завтра с 10:00 до 12:00 работа",
            title="Работа",
            scheduled_date=date(2026, 8, 4),
            scheduled_time=time(10, 0),
            scheduled_end_time=time(12, 0),
            duration_minutes=120,
            confidence=1.0,
        )
        client = TaskApiClient(
            base_url="http://task-api.test",
            transport=httpx.MockTransport(handler),
        )

        await client.create_task(
            extraction=extraction,
            user_id=7,
            chat_id=11,
            confirmation_token="range-token",
        )

        self.assertEqual(captured["startMinute"], 600)
        self.assertEqual(captured["durationMinutes"], 120)
    async def test_loads_tasks_and_groups_for_report(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/tasks":
                return httpx.Response(200, json=[{"id": "task-1", "date": "2026-08-03"}])
            if request.url.path == "/api/v1/groups":
                return httpx.Response(200, json=[{"id": "group-1", "name": "Работа"}])
            if request.url.path == "/api/v1/goals":
                return httpx.Response(200, json=[{"id": "goal-1", "title": "Чтение"}])
            return httpx.Response(404)

        client = TaskApiClient(base_url="http://task-api.test", transport=httpx.MockTransport(handler))
        self.assertEqual((await client.list_tasks())[0]["id"], "task-1")
        self.assertEqual((await client.list_groups())[0]["id"], "group-1")
        self.assertEqual((await client.list_goals())[0]["id"], "goal-1")
    async def test_updates_and_deletes_only_through_shared_api(self) -> None:
        requests: list[httpx.Request] = []
        task = {"id": "task-1", "title": "Задача", "date": "2026-08-03"}

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "PUT":
                return httpx.Response(200, json=json.loads(request.content))
            return httpx.Response(204)

        client = TaskApiClient(base_url="http://task-api.test", transport=httpx.MockTransport(handler))
        self.assertEqual((await client.update_task(task))["id"], "task-1")
        await client.delete_task("task-1")
        self.assertEqual([(item.method, item.url.path) for item in requests], [
            ("PUT", "/api/v1/tasks/task-1"),
            ("DELETE", "/api/v1/tasks/task-1"),
        ])
    async def test_finance_report_uses_shared_finance_api(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/api/v1/finance/report":
                return httpx.Response(200, json={
                    "period": request.url.params.get("period"),
                    "expenseCents": 125000,
                    "totalBalanceCents": 5000000,
                    "averageDailyExpenseCents": 125000,
                    "categorySpend": [],
                    "dailySpend": [],
                })
            if request.url.path == "/api/v1/finance/summary":
                return httpx.Response(200, json={"totalBalanceCents": 5000000})
            return httpx.Response(404)

        client = TaskApiClient(base_url="http://task-api.test", transport=httpx.MockTransport(handler))
        report = await client.finance_report(7, "week")
        summary = await client.finance_summary(7)
        self.assertEqual(report["period"], "week")
        self.assertEqual(summary["totalBalanceCents"], 5000000)
        self.assertEqual(requests[0].url.params["period"], "week")

    async def test_subscription_endpoints_and_notifications(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/api/v1/subscription/me":
                return httpx.Response(200, json={
                    "plan": "free",
                    "status": "active",
                    "entitlements": {"smart_scheduling": False},
                    "limits": {"ai_actions_monthly": 20},
                    "usage": {"ai_actions_monthly": 3},
                })
            if request.url.path.endswith("/consume"):
                return httpx.Response(200, json={"key": "ai_actions_monthly", "used": 4})
            if request.url.path == "/api/v1/users/me/notifications":
                return httpx.Response(200, json=[{"id": 1, "title": "Full", "message": "Доступ выдан"}])
            if request.url.path == "/api/v1/users/me/notifications/1/delivered":
                return httpx.Response(204)
            return httpx.Response(404)

        client = TaskApiClient(base_url="http://task-api.test", transport=httpx.MockTransport(handler))
        subscription = await client.get_subscription(7)
        usage = await client.consume_subscription_usage(7, "ai_actions_monthly")
        notifications = await client.pending_notifications(7)
        await client.mark_notification_delivered(7, 1)

        self.assertEqual(subscription["plan"], "free")
        self.assertEqual(usage["used"], 4)
        self.assertEqual(notifications[0]["id"], 1)
        self.assertEqual(requests[-1].method, "POST")

    async def test_subscription_limit_keeps_status_code_and_detail(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"detail": "Monthly AI limit reached"})

        client = TaskApiClient(base_url="http://task-api.test", transport=httpx.MockTransport(handler))
        with self.assertRaises(TaskApiSubscriptionError) as caught:
            await client.consume_subscription_usage(7, "ai_actions_monthly")
        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(caught.exception.detail, "Monthly AI limit reached")

    async def test_wraps_http_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"detail": "unavailable"})

        client = TaskApiClient(
            base_url="http://task-api.test",
            transport=httpx.MockTransport(handler),
        )
        with self.assertRaises(TaskApiError):
            await client.create_task(
                extraction=self.extraction,
                user_id=7,
                chat_id=11,
                confirmation_token="token",
            )


    async def test_maps_priority_and_deadline_to_shared_contract(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(201, json=captured)

        extraction = TaskExtraction(
            intent="create_task",
            source_text="срочно отправить отчёт до завтра 18:00",
            title="Отправить отчёт",
            scheduled_date=date(2026, 8, 4),
            priority="high",
            deadline_date=date(2026, 8, 4),
            deadline_time=time(18, 0),
            confidence=1.0,
        )
        client = TaskApiClient(base_url="http://task-api.test", transport=httpx.MockTransport(handler))
        await client.create_task(
            extraction=extraction,
            user_id=7,
            chat_id=11,
            confirmation_token="deadline-token",
        )
        self.assertEqual(captured["priority"], "high")
        self.assertEqual(captured["deadlineDate"], "2026-08-04")
        self.assertEqual(captured["deadlineMinute"], 1080)
        self.assertIsNone(captured["startMinute"])

if __name__ == "__main__":
    unittest.main()