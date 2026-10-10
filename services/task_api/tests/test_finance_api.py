from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from services.task_api.app import create_app
from services.task_api.repository import SqliteTaskRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _AsgiTestClient:
    """Small synchronous facade over the supported async httpx ASGI transport."""

    def __init__(self, tmp_path: Path) -> None:
        self._app = create_app(
            SqliteTaskRepository(tmp_path / "planner.sqlite3")
        )

    def request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        async def send() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._app),
                base_url="http://task-api.test",
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def get(self, path: str, **kwargs: object) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: object) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: object) -> httpx.Response:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: object) -> httpx.Response:
        return self.request("DELETE", path, **kwargs)

    def close(self) -> None:
        pass


def _client(tmp_path: Path) -> _AsgiTestClient:
    return _AsgiTestClient(tmp_path)


class FinanceApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.client = _client(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.client.close()
        self.temporary.cleanup()
    def test_finance_accounts_transactions_and_summary(self) -> None:
        client = self.client
        now = _now()
        account = {
            "id": "main",
            "name": "Основная карта",
            "openingBalanceCents": 100_000_00,
            "colorHex": "#5B47F7",
            "isDefault": True,
            "isArchived": False,
            "createdAt": now,
            "updatedAt": now,
        }
        response = client.post("/api/v1/finance/accounts", json=account)
        assert response.status_code == 201, response.text
        transaction = {
            "id": "expense-1",
            "type": "expense",
            "amountCents": 1_250_00,
            "accountId": "main",
            "categoryId": "food",
            "note": "Продукты",
            "occurredAt": now,
            "createdAt": now,
        }
        response = client.post("/api/v1/finance/transactions", json=transaction)
        assert response.status_code == 201, response.text
        summary = client.get("/api/v1/finance/summary")
        assert summary.status_code == 200, summary.text
        data = summary.json()
        assert data["totalBalanceCents"] == 98_750_00
        assert data["monthExpenseCents"] == 1_250_00
        assert data["categorySpend"][0]["name"] == "Продукты"


    def test_transfer_changes_account_shares_but_not_expenses(self) -> None:
        client = self.client
        now = _now()
        for account_id, name, amount in (("card", "Карта", 100_000_00), ("savings", "Накопления", 20_000_00)):
            response = client.post("/api/v1/finance/accounts", json={
                "id": account_id, "name": name, "openingBalanceCents": amount,
                "colorHex": "#5B47F7", "isDefault": account_id == "card", "isArchived": False,
                "createdAt": now, "updatedAt": now,
            })
            assert response.status_code == 201
        response = client.post("/api/v1/finance/transactions", json={
            "id": "transfer-1", "type": "transfer", "amountCents": 10_000_00,
            "accountId": "card", "toAccountId": "savings", "categoryId": None,
            "note": "В накопления", "occurredAt": now, "createdAt": now,
        })
        assert response.status_code == 201, response.text
        data = client.get("/api/v1/finance/summary").json()
        assert data["totalBalanceCents"] == 120_000_00
        assert data["monthExpenseCents"] == 0
        balances = {item["account"]["id"]: item["balanceCents"] for item in data["accounts"]}
        assert balances == {"card": 90_000_00, "savings": 30_000_00}


    def test_payment_creates_calendar_tasks(self) -> None:
        client = self.client
        now = _now()
        response = client.post("/api/v1/finance/payments", json={
            "id": "rent", "title": "Аренда", "amountCents": 35_000_00,
            "dueDate": date.today().replace(day=min(date.today().day, 28)).isoformat(),
            "recurrence": "monthly", "accountId": None, "categoryId": "housing",
            "isActive": True, "createCalendarTask": True, "createdAt": now, "updatedAt": now,
        })
        assert response.status_code == 201, response.text
        tasks = client.get("/api/v1/tasks").json()
        generated = [task for task in tasks if task["id"].startswith("finance-payment-rent-")]
        assert len(generated) == 12
        assert all(task["title"] == "Оплатить: Аренда" for task in generated)


    def test_custom_category_can_be_created_and_used(self) -> None:
        client = self.client
        now = _now()
        response = client.post("/api/v1/finance/categories", json={
            "id": "coffee", "name": "Кофе", "colorHex": "#A66B3F",
            "icon": "category", "isSystem": False, "createdAt": now, "updatedAt": now,
        })
        assert response.status_code == 201, response.text
        account = client.post("/api/v1/finance/accounts", json={
            "id": "card", "name": "Карта", "openingBalanceCents": 10_000_00,
            "colorHex": "#5B47F7", "isDefault": True, "isArchived": False,
            "createdAt": now, "updatedAt": now,
        })
        assert account.status_code == 201, account.text
        spent = client.post("/api/v1/finance/transactions", json={
            "id": "coffee-1", "type": "expense", "amountCents": 350_00,
            "accountId": "card", "toAccountId": None, "categoryId": "coffee",
            "note": "Капучино", "occurredAt": now, "createdAt": now,
        })
        assert spent.status_code == 201, spent.text
        summary = client.get("/api/v1/finance/summary").json()
        assert summary["categorySpend"][0]["name"] == "Кофе"


    def test_finance_period_report_supports_day_week_month_year(self) -> None:
        client = self.client
        now = _now()
        assert client.post("/api/v1/finance/accounts", json={
            "id": "main", "name": "Карта", "openingBalanceCents": 30_000_00,
            "colorHex": "#5B47F7", "isDefault": True, "isArchived": False,
            "createdAt": now, "updatedAt": now,
        }).status_code == 201
        assert client.post("/api/v1/finance/transactions", json={
            "id": "expense-report", "type": "expense", "amountCents": 900_00,
            "accountId": "main", "categoryId": "food", "note": "Продукты",
            "occurredAt": now, "createdAt": now,
        }).status_code == 201
        for period in ("day", "week", "month", "year"):
            response = client.get("/api/v1/finance/report", params={"period": period})
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["period"] == period
            assert data["expenseCents"] == 900_00
            assert data["totalBalanceCents"] == 29_100_00


    def test_updating_goal_with_missing_account_returns_422(self) -> None:
        now = _now()
        goal = {
            "id": "reserve", "title": "Подушка", "targetCents": 30_000_00,
            "savedCents": 0, "dueDate": None, "linkedAccountId": None,
            "createdAt": now, "updatedAt": now,
        }
        self.assertEqual(
            self.client.post("/api/v1/finance/goals", json=goal).status_code, 201
        )
        changed = {**goal, "linkedAccountId": "missing", "updatedAt": _now()}
        response = self.client.put("/api/v1/finance/goals/reserve", json=changed)
        self.assertEqual(response.status_code, 422, response.text)
        stored = self.client.get("/api/v1/finance/goals").json()[0]
        self.assertIsNone(stored["linkedAccountId"])
    def test_income_linked_goal_and_debt_keep_real_balance_consistent(self) -> None:
        client = self.client
        now = _now()
        assert client.post("/api/v1/finance/accounts", json={
            "id": "savings", "name": "Накопительный", "openingBalanceCents": 10_000_00,
            "colorHex": "#21B657", "isDefault": True, "isArchived": False,
            "createdAt": now, "updatedAt": now,
        }).status_code == 201
        assert client.post("/api/v1/finance/transactions", json={
            "id": "income-1", "type": "income", "amountCents": 5_000_00,
            "accountId": "savings", "toAccountId": None, "categoryId": None,
            "note": "Пополнение", "occurredAt": now, "createdAt": now,
        }).status_code == 201
        assert client.post("/api/v1/finance/goals", json={
            "id": "reserve", "title": "Подушка", "targetCents": 30_000_00,
            "savedCents": 0, "dueDate": None, "linkedAccountId": "savings",
            "createdAt": now, "updatedAt": now,
        }).status_code == 201
        assert client.post("/api/v1/finance/debts", json={
            "id": "debt-1", "title": "За билеты", "person": "Иван",
            "direction": "owed_to_me", "amountCents": 2_000_00,
            "dueDate": None, "status": "open", "note": "",
            "createdAt": now, "updatedAt": now,
        }).status_code == 201
        summary = client.get("/api/v1/finance/summary").json()
        assert summary["totalBalanceCents"] == 15_000_00
        assert summary["goals"][0]["savedCents"] == 15_000_00
        assert summary["debts"][0]["amountCents"] == 2_000_00

    def test_payment_collision_rolls_back_without_deleting_user_task(self) -> None:
        client = self.client
        now = _now()
        due = date.today().replace(day=min(date.today().day, 28)).isoformat()
        conflicting_id = f"finance-payment-rent-{due}"
        user_task = {
            "id": conflicting_id,
            "title": "Моя обычная задача",
            "note": "Создана пользователем, не финансовый маркер",
            "date": due,
            "startMinute": None,
            "priority": "normal",
            "isCompleted": False,
            "createdAt": now,
            "updatedAt": now,
        }
        self.assertEqual(client.post("/api/v1/tasks", json=user_task).status_code, 201)

        payment = {
            "id": "rent",
            "title": "Аренда",
            "amountCents": 35_000_00,
            "dueDate": due,
            "recurrence": "once",
            "accountId": None,
            "categoryId": "housing",
            "isActive": True,
            "createCalendarTask": True,
            "createdAt": now,
            "updatedAt": now,
        }
        response = client.post("/api/v1/finance/payments", json=payment)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(client.get("/api/v1/finance/payments").json(), [])
        tasks = client.get("/api/v1/tasks").json()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["title"], "Моя обычная задача")

    def test_deleting_payment_preserves_same_prefix_user_task(self) -> None:
        client = self.client
        now = _now()
        due = date.today().replace(day=min(date.today().day, 28)).isoformat()
        payment = {
            "id": "rent",
            "title": "Аренда",
            "amountCents": 35_000_00,
            "dueDate": due,
            "recurrence": "once",
            "accountId": None,
            "categoryId": "housing",
            "isActive": False,
            "createCalendarTask": False,
            "createdAt": now,
            "updatedAt": now,
        }
        self.assertEqual(client.post("/api/v1/finance/payments", json=payment).status_code, 201)
        user_task = {
            "id": "manual-finance-note",
            "title": "Обычная задача с похожим ID",
            "note": "Пользовательская заметка [finance-payment:rent]",
            "date": due,
            "startMinute": None,
            "priority": "normal",
            "isCompleted": False,
            "createdAt": now,
            "updatedAt": now,
        }
        self.assertEqual(client.post("/api/v1/tasks", json=user_task).status_code, 201)

        self.assertEqual(client.delete("/api/v1/finance/payments/rent").status_code, 204)
        tasks = client.get("/api/v1/tasks").json()
        self.assertEqual([task["id"] for task in tasks], [user_task["id"]])
    def test_payment_update_collision_returns_422_and_restores_previous_state(self) -> None:
        now = _now()
        due = date.today().replace(day=min(date.today().day, 28)).isoformat()
        payment = {
            "id": "rent",
            "title": "Черновик аренды",
            "amountCents": 35_000_00,
            "dueDate": due,
            "recurrence": "once",
            "accountId": None,
            "categoryId": "housing",
            "isActive": False,
            "createCalendarTask": False,
            "createdAt": now,
            "updatedAt": now,
        }
        self.assertEqual(
            self.client.post("/api/v1/finance/payments", json=payment).status_code,
            201,
        )
        task_id = f"finance-payment-rent-{due}"
        task = {
            "id": task_id,
            "title": "Пользовательская задача",
            "note": "Не принадлежит финансовому модулю",
            "date": due,
            "startMinute": None,
            "priority": "normal",
            "isCompleted": False,
            "createdAt": now,
            "updatedAt": now,
        }
        self.assertEqual(self.client.post("/api/v1/tasks", json=task).status_code, 201)

        changed = {
            **payment,
            "title": "Активная аренда",
            "isActive": True,
            "createCalendarTask": True,
            "updatedAt": _now(),
        }
        response = self.client.put("/api/v1/finance/payments/rent", json=changed)
        self.assertEqual(response.status_code, 422, response.text)
        stored = self.client.get("/api/v1/finance/payments").json()[0]
        self.assertEqual(stored["title"], "Черновик аренды")
        self.assertFalse(stored["isActive"])
        self.assertFalse(stored["createCalendarTask"])
        tasks = self.client.get("/api/v1/tasks").json()
        self.assertEqual([(item["id"], item["title"]) for item in tasks], [(task_id, task["title"])])

    def test_finance_titles_cannot_be_only_whitespace(self) -> None:
        now = _now()
        common_timestamps = {"createdAt": now, "updatedAt": now}
        payloads = (
            ("/api/v1/finance/goals", {
                "id": "blank-goal", "title": "   ", "targetCents": 10_000,
                "savedCents": 0, "dueDate": None, "linkedAccountId": None,
                **common_timestamps,
            }),
            ("/api/v1/finance/payments", {
                "id": "blank-payment", "title": " \t ", "amountCents": 10_000,
                "dueDate": date.today().isoformat(), "recurrence": "once",
                "accountId": None, "categoryId": None, "isActive": False,
                "createCalendarTask": False, **common_timestamps,
            }),
            ("/api/v1/finance/debts", {
                "id": "blank-debt", "title": "\n ", "person": "",
                "direction": "owed_to_me", "amountCents": 10_000,
                "dueDate": None, "status": "open", "note": "",
                **common_timestamps,
            }),
        )
        for endpoint, payload in payloads:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(endpoint, json=payload)
                self.assertEqual(response.status_code, 422, response.text)

    def test_payment_id_boundary_keeps_generated_task_id_valid(self) -> None:
        now = _now()
        due = date.today().isoformat()
        valid_id = "p" * 100
        payload = {
            "id": valid_id,
            "title": "Граничный платёж",
            "amountCents": 10_000,
            "dueDate": due,
            "recurrence": "once",
            "accountId": None,
            "categoryId": None,
            "isActive": True,
            "createCalendarTask": True,
            "createdAt": now,
            "updatedAt": now,
        }
        response = self.client.post("/api/v1/finance/payments", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        generated_id = self.client.get("/api/v1/tasks").json()[0]["id"]
        self.assertLessEqual(len(generated_id), 128)

        payload["id"] = "p" * 101
        response = self.client.post("/api/v1/finance/payments", json=payload)
        self.assertEqual(response.status_code, 422, response.text)
    def test_manual_transaction_cannot_use_reserved_settlement_prefix(self) -> None:
        now = _now()
        self.assertEqual(self.client.post("/api/v1/finance/accounts", json={
            "id": "main", "name": "Карта", "openingBalanceCents": 100_000,
            "colorHex": "#5B47F7", "isDefault": True, "isArchived": False,
            "createdAt": now, "updatedAt": now,
        }).status_code, 201)
        response = self.client.post("/api/v1/finance/transactions", json={
            "id": "finance-settle-user-controlled", "type": "expense",
            "amountCents": 10_000, "accountId": "main", "toAccountId": None,
            "categoryId": "food", "note": "Ручная операция",
            "occurredAt": now, "createdAt": now,
        })
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.get("/api/v1/finance/transactions").json(), [])
    def test_existing_payment_database_migrates_recurrence_day(self) -> None:
        legacy = tempfile.TemporaryDirectory()
        try:
            path = Path(legacy.name) / "planner.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute("""CREATE TABLE finance_payments (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, amount_cents INTEGER NOT NULL,
                    due_date TEXT NOT NULL, recurrence TEXT NOT NULL, account_id TEXT,
                    category_id TEXT, is_active INTEGER NOT NULL,
                    create_calendar_task INTEGER NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )""")
                connection.execute(
                    "INSERT INTO finance_payments VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "legacy-rent", "Аренда", 1_000_000, "2027-01-31", "monthly",
                        None, None, 1, 0, _now(), _now(),
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            client = _client(Path(legacy.name))
            try:
                response = client.get("/api/v1/finance/payments")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()[0]["recurrenceDay"], 31)
            finally:
                client.close()
        finally:
            legacy.cleanup()
    def test_settling_monthly_payment_is_atomic_idempotent_and_preserves_day(self) -> None:
        now = _now()
        self.assertEqual(self.client.post("/api/v1/finance/accounts", json={
            "id": "main", "name": "Карта", "openingBalanceCents": 100_000_00,
            "colorHex": "#5B47F7", "isDefault": True, "isArchived": False,
            "createdAt": now, "updatedAt": now,
        }).status_code, 201)
        payment = {
            "id": "month-end", "title": "Аренда", "amountCents": 10_000_00,
            "dueDate": "2027-01-31", "recurrence": "monthly", "recurrenceDay": 31,
            "accountId": "main", "categoryId": "housing", "isActive": True,
            "createCalendarTask": True, "createdAt": now, "updatedAt": now,
        }
        self.assertEqual(
            self.client.post("/api/v1/finance/payments", json=payment).status_code, 201
        )

        settle = {"expectedDueDate": "2027-01-31", "paidAt": "2027-01-31T12:00:00Z"}
        first = self.client.post("/api/v1/finance/payments/month-end/settle", json=settle)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json()["created"])
        self.assertEqual(first.json()["payment"]["dueDate"], "2027-02-28")
        self.assertEqual(first.json()["payment"]["recurrenceDay"], 31)

        repeated = self.client.post("/api/v1/finance/payments/month-end/settle", json=settle)
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertFalse(repeated.json()["created"])
        transactions = self.client.get("/api/v1/finance/transactions").json()
        self.assertEqual(len(transactions), 1)

        second = self.client.post("/api/v1/finance/payments/month-end/settle", json={
            "expectedDueDate": "2027-02-28", "paidAt": "2027-02-28T12:00:00Z",
        })
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["payment"]["dueDate"], "2027-03-31")
        transactions = self.client.get("/api/v1/finance/transactions").json()
        self.assertEqual(len(transactions), 2)

    def test_settlement_validation_never_creates_partial_transaction(self) -> None:
        now = _now()
        payment = {
            "id": "without-account", "title": "Счёт", "amountCents": 5_000_00,
            "dueDate": "2027-04-15", "recurrence": "once",
            "accountId": None, "categoryId": None, "isActive": True,
            "createCalendarTask": True, "createdAt": now, "updatedAt": now,
        }
        self.assertEqual(
            self.client.post("/api/v1/finance/payments", json=payment).status_code, 201
        )
        response = self.client.post(
            "/api/v1/finance/payments/without-account/settle",
            json={"expectedDueDate": "2027-04-15", "paidAt": "2027-04-15T10:00:00Z"},
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.get("/api/v1/finance/transactions").json(), [])
        stored = self.client.get("/api/v1/finance/payments").json()[0]
        self.assertTrue(stored["isActive"])
        self.assertEqual(stored["dueDate"], "2027-04-15")

    def test_settlement_rolls_back_finance_when_next_calendar_task_conflicts(self) -> None:
        now = _now()
        self.assertEqual(self.client.post("/api/v1/finance/accounts", json={
            "id": "main", "name": "Карта", "openingBalanceCents": 100_000_00,
            "colorHex": "#5B47F7", "isDefault": True, "isArchived": False,
            "createdAt": now, "updatedAt": now,
        }).status_code, 201)
        payment = {
            "id": "rent", "title": "Аренда", "amountCents": 10_000_00,
            "dueDate": "2027-01-15", "recurrence": "monthly", "recurrenceDay": 15,
            "accountId": "main", "categoryId": "housing", "isActive": True,
            "createCalendarTask": True, "createdAt": now, "updatedAt": now,
        }
        self.assertEqual(
            self.client.post("/api/v1/finance/payments", json=payment).status_code, 201
        )
        # Remove generated tasks, then reserve the exact first ID of the next schedule.
        existing_tasks = self.client.get("/api/v1/tasks").json()
        for task in existing_tasks:
            self.assertEqual(self.client.delete(f"/api/v1/tasks/{task['id']}").status_code, 204)
        conflicting_id = "finance-payment-rent-2027-02-15"
        self.assertEqual(self.client.post("/api/v1/tasks", json={
            "id": conflicting_id, "title": "Пользовательская задача",
            "note": "Без финансового маркера", "date": "2027-02-15",
            "startMinute": None, "priority": "normal", "isCompleted": False,
            "createdAt": now, "updatedAt": now,
        }).status_code, 201)

        response = self.client.post("/api/v1/finance/payments/rent/settle", json={
            "expectedDueDate": "2027-01-15", "paidAt": "2027-01-15T10:00:00Z",
        })
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.get("/api/v1/finance/transactions").json(), [])
        stored = self.client.get("/api/v1/finance/payments").json()[0]
        self.assertEqual(stored["dueDate"], "2027-01-15")
        tasks = self.client.get("/api/v1/tasks").json()
        self.assertEqual([(task["id"], task["title"]) for task in tasks], [
            (conflicting_id, "Пользовательская задача")
        ])
if __name__ == "__main__":
    unittest.main()