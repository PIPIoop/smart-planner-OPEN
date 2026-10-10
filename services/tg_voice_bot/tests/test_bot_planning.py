from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from bot import CONFIRMATION_STORE_KEY, TASK_API_CLIENT_KEY, _offer_best_slots, _save_pending
from confirmation_store import ConfirmationStore, PendingTask
from task_api_client import TaskApiClient
from task_extractor import TaskExtraction


class BotPlanningTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.zone = ZoneInfo("Asia/Yekaterinburg")
        self.now = datetime(2026, 8, 3, 10, 15, tzinfo=self.zone)
        self.client = TaskApiClient(base_url="http://task-api.test")
        self.client.list_tasks = AsyncMock(return_value=[])
        self.client.create_task = AsyncMock(return_value={"id": "created"})
        self.client.get_subscription = AsyncMock(return_value={
            "plan": "plus",
            "status": "active",
            "entitlements": {
                "smart_scheduling": True,
                "multi_task_recognition": True,
                "advanced_reports": True,
                "finance": False,
                "finance_telegram": False,
            },
            "limits": {},
            "usage": {},
        })
        self.store = ConfirmationStore()
        self.context = SimpleNamespace(
            application=SimpleNamespace(
                bot_data={
                    TASK_API_CLIENT_KEY: self.client,
                    CONFIRMATION_STORE_KEY: self.store,
                }
            ),
            bot=SimpleNamespace(send_message=AsyncMock()),
        )
        self.query = SimpleNamespace(edit_message_text=AsyncMock(), answer=AsyncMock())

    def _pending(self, extraction: TaskExtraction) -> PendingTask:
        return PendingTask(
            token="token",
            user_id=7,
            chat_id=77,
            extraction=extraction,
            created_at=self.now,
            expires_at=self.now + timedelta(minutes=15),
        )

    async def test_deadline_only_task_can_be_scheduled_before_deadline_day(self) -> None:
        extraction = TaskExtraction(
            intent="create_task",
            source_text="отправить отчёт до пятницы",
            title="Отправить отчёт",
            scheduled_date=date(2026, 8, 7),
            duration_minutes=60,
            deadline_date=date(2026, 8, 7),
            warnings=("date_inferred_from_deadline", "time_not_found"),
            confidence=0.9,
        )

        await _offer_best_slots(
            query=self.query,
            context=self.context,
            pending=self._pending(extraction),
            now=self.now,
        )

        markup = self.query.edit_message_text.await_args.kwargs["reply_markup"]
        first_callback = markup.inline_keyboard[0][0].callback_data
        self.assertIn("20260803", first_callback)

    async def test_final_save_rechecks_calendar_and_never_creates_overlap(self) -> None:
        extraction = TaskExtraction(
            intent="create_task",
            source_text="сегодня в 12 встреча на час",
            title="Встреча",
            scheduled_date=date(2026, 8, 3),
            scheduled_time=time(12, 0),
            scheduled_end_time=time(13, 0),
            duration_minutes=60,
            confidence=1.0,
        )
        self.client.list_tasks = AsyncMock(
            return_value=[
                {
                    "id": "busy",
                    "title": "Уже занято",
                    "date": "2026-08-03",
                    "startMinute": 12 * 60,
                    "durationMinutes": 60,
                    "isCompleted": False,
                }
            ]
        )

        await _save_pending(
            query=self.query,
            context=self.context,
            pending=self._pending(extraction),
            now=self.now,
        )

        self.client.create_task.assert_not_awaited()
        call = self.query.edit_message_text.await_args
        rendered = call.kwargs.get("text") or call.args[0]
        self.assertIn("Календарь изменился", rendered)


if __name__ == "__main__":
    unittest.main()
