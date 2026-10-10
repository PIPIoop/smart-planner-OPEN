from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from services.task_api.app import create_app
from services.task_api.security import derive_user_access_token
from services.task_api.users import MultiTenantStore


class SubscriptionApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MultiTenantStore(Path(self.tmp.name) / "tasks.sqlite3")
        self.service_token = "x" * 48
        app = create_app(
            multi_tenant_store=self.store,
            service_token=self.service_token,
            web_admin_password="admin-pass",
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )
        service_headers = {"Authorization": f"Bearer {self.service_token}"}
        await self.client.post(
            "/api/v1/users/bootstrap-admin",
            headers=service_headers,
            json={"telegramUserId": "100", "username": "admin", "displayName": "Admin"},
        )
        await self.client.post(
            "/api/v1/users/requests",
            headers=service_headers,
            json={"telegramUserId": "200", "username": "user", "displayName": "User"},
        )
        await self.client.post(
            "/api/v1/users/200/status/active", headers=self.headers("100")
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.tmp.cleanup()

    def headers(self, user_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {derive_user_access_token(self.service_token, user_id)}",
            "X-User-Id": user_id,
        }

    async def test_new_user_gets_full_trial_and_role_user(self) -> None:
        me = await self.client.get("/api/v1/users/me", headers=self.headers("200"))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["role"], "user")
        self.assertEqual(me.json()["subscriptionPlan"], "full")
        self.assertEqual(me.json()["subscriptionStatus"], "trial")

        sub = await self.client.get("/api/v1/subscription/me", headers=self.headers("200"))
        self.assertEqual(sub.status_code, 200)
        self.assertTrue(sub.json()["entitlements"]["finance"])
        self.assertFalse(sub.json()["financeReadOnly"])

    async def test_admin_can_reset_to_free_finance_becomes_read_only(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        account = {
            "id": "card", "name": "Карта", "openingBalanceCents": 10_000_50,
            "colorHex": "#5B47F7", "isDefault": True, "isArchived": False,
            "createdAt": now, "updatedAt": now,
        }
        created = await self.client.post(
            "/api/v1/finance/accounts", headers=self.headers("200"), json=account
        )
        self.assertEqual(created.status_code, 201, created.text)

        reset = await self.client.delete(
            "/api/v1/admin/users/200/subscription", headers=self.headers("100")
        )
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.json()["plan"], "free")

        readable = await self.client.get(
            "/api/v1/finance/summary", headers=self.headers("200")
        )
        self.assertEqual(readable.status_code, 200)
        self.assertEqual(readable.json()["totalBalanceCents"], 10_000_50)

        blocked = await self.client.post(
            "/api/v1/finance/transactions",
            headers=self.headers("200"),
            json={
                "id": "expense", "type": "expense", "amountCents": 100_25,
                "accountId": "card", "toAccountId": None, "categoryId": "food",
                "note": "кофе", "occurredAt": now, "createdAt": now,
            },
        )
        self.assertEqual(blocked.status_code, 403)

    async def test_free_limits_and_temporary_override(self) -> None:
        await self.client.delete(
            "/api/v1/admin/users/200/subscription", headers=self.headers("100")
        )
        now = datetime.now(timezone.utc).isoformat()
        for index in range(3):
            response = await self.client.post(
                "/api/v1/groups",
                headers=self.headers("200"),
                json={
                    "id": f"limit-group-{index}", "name": f"Group {index}", "colorHex": ["#5B47F7", "#2F7CF6", "#21B657"][index],
                    "createdAt": now, "updatedAt": now,
                },
            )
            self.assertEqual(response.status_code, 201, response.text)
        blocked = await self.client.post(
            "/api/v1/groups",
            headers=self.headers("200"),
            json={
                "id": "limit-group-3", "name": "Group 3", "colorHex": "#F29D38",
                "createdAt": now, "updatedAt": now,
            },
        )
        self.assertEqual(blocked.status_code, 403)

        override = await self.client.post(
            "/api/v1/admin/users/200/overrides",
            headers=self.headers("100"),
            json={
                "key": "groups", "kind": "limit_bonus", "intValue": 2,
                "expiresAt": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                "reason": "Бонус за тестирование",
            },
        )
        self.assertEqual(override.status_code, 201, override.text)
        allowed = await self.client.post(
            "/api/v1/groups",
            headers=self.headers("200"),
            json={
                "id": "limit-group-3", "name": "Group 3", "colorHex": "#F29D38",
                "createdAt": now, "updatedAt": now,
            },
        )
        self.assertEqual(allowed.status_code, 201, allowed.text)
        notifications = await self.client.get(
            "/api/v1/users/me/notifications", headers=self.headers("200")
        )
        self.assertGreaterEqual(len(notifications.json()), 2)

    async def test_admin_cross_user_calendar_is_read_only(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        task = {
            "id": "task-x", "title": "Нельзя создать", "note": "", "date": "2026-08-08",
            "startMinute": None, "priority": "normal", "isCompleted": False,
            "createdAt": now, "updatedAt": now,
        }
        response = await self.client.post(
            "/api/v1/tasks?userId=200", headers=self.headers("100"), json=task
        )
        self.assertEqual(response.status_code, 403)
        import_response = await self.client.put(
            "/api/v1/planner-data?userId=200",
            headers=self.headers("100"),
            json={"tasks": [], "goals": [], "groups": []},
        )
        self.assertEqual(import_response.status_code, 403)
        view = await self.client.get(
            "/api/v1/tasks?userId=200", headers=self.headers("100")
        )
        self.assertEqual(view.status_code, 200)

    async def test_admin_can_grant_trial_and_audit_is_recorded(self) -> None:
        await self.client.delete(
            "/api/v1/admin/users/200/subscription", headers=self.headers("100")
        )
        response = await self.client.post(
            "/api/v1/admin/users/200/trial",
            headers=self.headers("100"),
            json={"days": 21},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "trial")
        audit = await self.client.get(
            "/api/v1/admin/users/200/audit", headers=self.headers("100")
        )
        self.assertEqual(audit.status_code, 200)
        actions = [item["action"] for item in audit.json()]
        self.assertIn("trial.granted", actions)
        self.assertIn("subscription.reset_to_free", actions)

    async def test_free_ai_usage_stops_after_twenty_actions(self) -> None:
        await self.client.delete(
            "/api/v1/admin/users/200/subscription", headers=self.headers("100")
        )
        for _ in range(20):
            response = await self.client.post(
                "/api/v1/subscription/usage/ai_actions_monthly/consume",
                headers=self.headers("200"),
            )
            self.assertEqual(response.status_code, 200, response.text)
        blocked = await self.client.post(
            "/api/v1/subscription/usage/ai_actions_monthly/consume",
            headers=self.headers("200"),
        )
        self.assertEqual(blocked.status_code, 429)

    async def test_temporary_finance_override_restores_write_access(self) -> None:
        await self.client.delete(
            "/api/v1/admin/users/200/subscription", headers=self.headers("100")
        )
        override = await self.client.post(
            "/api/v1/admin/users/200/overrides",
            headers=self.headers("100"),
            json={
                "key": "finance",
                "kind": "entitlement",
                "boolValue": True,
                "expiresAt": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                "reason": "Временный доступ",
            },
        )
        self.assertEqual(override.status_code, 201, override.text)
        now = datetime.now(timezone.utc).isoformat()
        account = await self.client.post(
            "/api/v1/finance/accounts",
            headers=self.headers("200"),
            json={
                "id": "kopeks-card",
                "name": "Карта",
                "openingBalanceCents": 123_456,
                "colorHex": "#5B47F7",
                "isDefault": True,
                "isArchived": False,
                "createdAt": now,
                "updatedAt": now,
            },
        )
        self.assertEqual(account.status_code, 201, account.text)
        summary = await self.client.get("/api/v1/finance/summary", headers=self.headers("200"))
        self.assertEqual(summary.json()["totalBalanceCents"], 123_456)

    async def test_repeated_payment_settlement_consumes_one_usage_unit(self) -> None:
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
        account = await self.client.post(
            "/api/v1/finance/accounts",
            headers=self.headers("200"),
            json={
                "id": "settlement-card", "name": "Карта",
                "openingBalanceCents": 10_000_00, "colorHex": "#5B47F7",
                "isDefault": True, "isArchived": False,
                "createdAt": timestamp, "updatedAt": timestamp,
            },
        )
        self.assertEqual(account.status_code, 201, account.text)
        due_date = now.date().isoformat()
        payment = await self.client.post(
            "/api/v1/finance/payments",
            headers=self.headers("200"),
            json={
                "id": "settlement", "title": "Подписка",
                "amountCents": 500_00, "dueDate": due_date,
                "recurrence": "once", "accountId": "settlement-card",
                "categoryId": "subscriptions", "isActive": True,
                "createCalendarTask": True,
                "createdAt": timestamp, "updatedAt": timestamp,
            },
        )
        self.assertEqual(payment.status_code, 201, payment.text)
        payload = {"expectedDueDate": due_date, "paidAt": timestamp}
        first = await self.client.post(
            "/api/v1/finance/payments/settlement/settle",
            headers=self.headers("200"), json=payload,
        )
        repeated = await self.client.post(
            "/api/v1/finance/payments/settlement/settle",
            headers=self.headers("200"), json=payload,
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json()["created"])
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertFalse(repeated.json()["created"])
        usage = self.store.subscriptions.usage_snapshot("200")
        self.assertEqual(usage["finance_transactions_monthly"], 1)

    async def test_failed_finance_transaction_refunds_reserved_usage(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        failed = await self.client.post(
            "/api/v1/finance/transactions",
            headers=self.headers("200"),
            json={
                "id": "invalid", "type": "expense", "amountCents": 500_00,
                "accountId": "missing", "toAccountId": None,
                "categoryId": "food", "note": "Не должно сохраниться",
                "occurredAt": now, "createdAt": now,
            },
        )
        self.assertEqual(failed.status_code, 422, failed.text)
        usage = self.store.subscriptions.usage_snapshot("200")
        self.assertNotIn("finance_transactions_monthly", usage)
    async def test_expired_paid_period_falls_back_to_free_with_system_audit(self) -> None:
        expired_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        assigned = await self.client.put(
            "/api/v1/admin/users/200/subscription",
            headers=self.headers("100"),
            json={
                "plan": "full",
                "status": "active",
                "billingPeriod": "monthly",
                "expiresAt": expired_at,
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)

        snapshot = await self.client.get(
            "/api/v1/subscription/me", headers=self.headers("200")
        )
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(snapshot.json()["plan"], "free")
        self.assertTrue(snapshot.json()["financeReadOnly"])

        audit = await self.client.get(
            "/api/v1/admin/users/200/audit", headers=self.headers("100")
        )
        actions = [item["action"] for item in audit.json()]
        self.assertIn("subscription.subscription_expired", actions)
        notifications = await self.client.get(
            "/api/v1/users/me/notifications", headers=self.headers("200")
        )
        self.assertTrue(any("только для чтения" in item["message"] for item in notifications.json()))

    async def test_past_due_keeps_access_during_three_day_grace(self) -> None:
        expires_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        assigned = await self.client.put(
            "/api/v1/admin/users/200/subscription",
            headers=self.headers("100"),
            json={
                "plan": "plus",
                "status": "past_due",
                "billingPeriod": "monthly",
                "expiresAt": expires_at,
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        snapshot = await self.client.get(
            "/api/v1/subscription/me", headers=self.headers("200")
        )
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(snapshot.json()["plan"], "plus")
        self.assertEqual(snapshot.json()["status"], "past_due")
        self.assertIsNotNone(snapshot.json()["graceEndsAt"])
        self.assertTrue(snapshot.json()["entitlements"]["smart_scheduling"])

    async def test_temporary_override_expires_with_audit_and_notification(self) -> None:
        base = datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc)
        self.store.subscriptions._now = lambda: base
        override = await self.client.post(
            "/api/v1/admin/users/200/overrides",
            headers=self.headers("100"),
            json={
                "key": "advanced_reports",
                "kind": "entitlement",
                "boolValue": True,
                "expiresAt": (base + timedelta(days=1)).isoformat(),
                "reason": "Тестовый доп",
            },
        )
        self.assertEqual(override.status_code, 201, override.text)

        self.store.subscriptions._now = lambda: base + timedelta(days=2)
        snapshot = await self.client.get(
            "/api/v1/subscription/me", headers=self.headers("200")
        )
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(snapshot.json()["overrides"], [])
        audit = await self.client.get(
            "/api/v1/admin/users/200/audit", headers=self.headers("100")
        )
        self.assertIn("override.expired", [item["action"] for item in audit.json()])
        notifications = await self.client.get(
            "/api/v1/users/me/notifications", headers=self.headers("200")
        )
        self.assertTrue(any("Срок дополнительной возможности" in item["message"] for item in notifications.json()))

    async def test_admin_cannot_mutate_other_users_finances(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        response = await self.client.post(
            "/api/v1/finance/accounts?userId=200",
            headers=self.headers("100"),
            json={
                "id": "admin-write",
                "name": "Нельзя",
                "openingBalanceCents": 10_050,
                "colorHex": "#5B47F7",
                "isDefault": True,
                "isArchived": False,
                "createdAt": now,
                "updatedAt": now,
            },
        )
        self.assertEqual(response.status_code, 403)
        readable = await self.client.get(
            "/api/v1/finance/summary?userId=200", headers=self.headers("100")
        )
        self.assertEqual(readable.status_code, 200)


if __name__ == "__main__":
    unittest.main()
