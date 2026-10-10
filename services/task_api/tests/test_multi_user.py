from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

from services.task_api.app import create_app
from services.task_api.security import derive_user_access_token
from services.task_api.users import MultiTenantStore


class MultiUserApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temporary.name) / "tasks.sqlite3"
        self.service_token = "s" * 48
        self.web_admin_password = "web-admin-password-for-tests"
        self.store = MultiTenantStore(self.base_path)
        app = create_app(
            multi_tenant_store=self.store,
            service_token=self.service_token,
            web_admin_password=self.web_admin_password,
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://task-api.test",
        )
        self.service_headers = {"Authorization": f"Bearer {self.service_token}"}

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.temporary.cleanup()

    def user_headers(self, user_id: str) -> dict[str, str]:
        token = derive_user_access_token(self.service_token, user_id)
        return {"Authorization": f"Bearer {token}", "X-User-Id": user_id}

    def task(self, task_id: str, title: str) -> dict[str, object]:
        timestamp = datetime(2026, 8, 4, 10, tzinfo=timezone.utc).isoformat()
        return {
            "id": task_id,
            "title": title,
            "note": "",
            "date": "2026-08-05",
            "startMinute": None,
            "priority": "normal",
            "isCompleted": False,
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }

    async def bootstrap_and_approve(self) -> None:
        admin = {
            "telegramUserId": "100",
            "username": "admin",
            "displayName": "Admin",
        }
        response = await self.client.post(
            "/api/v1/users/bootstrap-admin",
            headers=self.service_headers,
            json=admin,
        )
        self.assertEqual(response.status_code, 200)
        request = await self.client.post(
            "/api/v1/users/requests",
            headers=self.service_headers,
            json={
                "telegramUserId": "200",
                "username": "user",
                "displayName": "User",
            },
        )
        self.assertEqual(request.status_code, 201)
        approved = await self.client.post(
            "/api/v1/users/200/status/active",
            headers=self.user_headers("100"),
        )
        self.assertEqual(approved.status_code, 200)

    async def test_web_session_is_short_lived_admin_credential(self) -> None:
        await self.bootstrap_and_approve()
        rejected = await self.client.post(
            "/api/v1/web/session", json={"password": "wrong"}
        )
        self.assertEqual(rejected.status_code, 401)

        login = await self.client.post(
            "/api/v1/web/session", json={"password": self.web_admin_password}
        )
        self.assertEqual(login.status_code, 200)
        session = login.json()
        headers = {
            "Authorization": f"Session {session['session_token']}",
            "X-User-Id": session["admin_user_id"],
        }
        users = await self.client.get("/api/v1/users", headers=headers)
        selected_calendar = await self.client.get(
            "/api/v1/tasks?userId=200", headers=headers
        )
        self.assertEqual(users.status_code, 200)
        self.assertEqual(selected_calendar.status_code, 200)
    async def test_requires_valid_scoped_credential(self) -> None:
        await self.bootstrap_and_approve()
        missing = await self.client.get("/api/v1/tasks")
        forged = await self.client.get(
            "/api/v1/tasks",
            headers={"Authorization": "Bearer wrong", "X-User-Id": "200"},
        )
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(forged.status_code, 401)

    async def test_calendars_are_isolated_and_ids_can_repeat(self) -> None:
        await self.bootstrap_and_approve()
        admin_create = await self.client.post(
            "/api/v1/tasks",
            headers=self.user_headers("100"),
            json=self.task("same-id", "Задача администратора"),
        )
        user_create = await self.client.post(
            "/api/v1/tasks",
            headers=self.user_headers("200"),
            json=self.task("same-id", "Задача пользователя"),
        )
        self.assertEqual(admin_create.status_code, 201)
        self.assertEqual(user_create.status_code, 201)

        admin_tasks = await self.client.get(
            "/api/v1/tasks", headers=self.user_headers("100")
        )
        user_tasks = await self.client.get(
            "/api/v1/tasks", headers=self.user_headers("200")
        )
        self.assertEqual([item["title"] for item in admin_tasks.json()], ["Задача администратора"])
        self.assertEqual([item["title"] for item in user_tasks.json()], ["Задача пользователя"])

        forbidden = await self.client.get(
            "/api/v1/tasks?userId=100",
            headers=self.user_headers("200"),
        )
        self.assertEqual(forbidden.status_code, 403)

        admin_view = await self.client.get(
            "/api/v1/tasks?userId=200",
            headers=self.user_headers("100"),
        )
        self.assertEqual(admin_view.status_code, 200)
        self.assertEqual(admin_view.json()[0]["title"], "Задача пользователя")

    async def test_finance_data_is_isolated_per_user(self) -> None:
        await self.bootstrap_and_approve()
        now = datetime(2026, 8, 8, 10, tzinfo=timezone.utc).isoformat()
        for user_id, account_id, amount in (("100", "admin-card", 50_000_00), ("200", "user-card", 12_000_00)):
            created = await self.client.post(
                "/api/v1/finance/accounts",
                headers=self.user_headers(user_id),
                json={
                    "id": account_id, "name": "Карта", "openingBalanceCents": amount,
                    "colorHex": "#5B47F7", "isDefault": True, "isArchived": False,
                    "createdAt": now, "updatedAt": now,
                },
            )
            self.assertEqual(created.status_code, 201)

        admin_summary = await self.client.get("/api/v1/finance/summary", headers=self.user_headers("100"))
        user_summary = await self.client.get("/api/v1/finance/summary", headers=self.user_headers("200"))
        self.assertEqual(admin_summary.json()["totalBalanceCents"], 50_000_00)
        self.assertEqual(user_summary.json()["totalBalanceCents"], 12_000_00)

        forbidden = await self.client.get(
            "/api/v1/finance/summary?userId=100", headers=self.user_headers("200")
        )
        self.assertEqual(forbidden.status_code, 403)

        admin_view = await self.client.get(
            "/api/v1/finance/summary?userId=200", headers=self.user_headers("100")
        )
        self.assertEqual(admin_view.status_code, 200)
        self.assertEqual(admin_view.json()["totalBalanceCents"], 12_000_00)

    async def test_admin_statuses_stats_and_permanent_delete(self) -> None:
        await self.bootstrap_and_approve()
        await self.client.post(
            "/api/v1/tasks",
            headers=self.user_headers("200"),
            json=self.task("task-1", "Пользовательская задача"),
        )
        users = await self.client.get(
            "/api/v1/users", headers=self.user_headers("100")
        )
        user = next(item for item in users.json() if item["telegramUserId"] == "200")
        self.assertEqual(user["taskCount"], 1)

        blocked = await self.client.post(
            "/api/v1/users/200/status/blocked",
            headers=self.user_headers("100"),
        )
        self.assertEqual(blocked.status_code, 200)
        denied = await self.client.get(
            "/api/v1/tasks", headers=self.user_headers("200")
        )
        self.assertEqual(denied.status_code, 403)

        deleted = await self.client.delete(
            "/api/v1/users/200", headers=self.user_headers("100")
        )
        self.assertEqual(deleted.status_code, 204)
        missing = await self.client.get(
            "/api/v1/users/me", headers=self.user_headers("200")
        )
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()