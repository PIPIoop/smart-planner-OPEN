from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.ext import ApplicationHandlerStop

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from bot import (
    SETTINGS_KEY,
    TASK_API_CLIENT_KEY,
    access_guard_handler,
    admin_callback_handler,
    admin_handler,
)
from config import Settings
from task_api_client import TaskApiClient


def _settings(admin_id: int = 123456789) -> Settings:
    return Settings(
        telegram_bot_token="test-token",
        telegram_admin_user_id=admin_id,
        whisper_model="small",
        whisper_language="ru",
        whisper_device="cpu",
        whisper_compute_type="int8",
        max_voice_duration_seconds=300,
        task_api_url="http://127.0.0.1:8080",
        task_api_timeout_seconds=10.0,
        task_api_service_token="x" * 32,
        app_timezone="Asia/Yekaterinburg",
        app_locale="ru-RU",
    )


def _update(user_id: int, message: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        effective_user=SimpleNamespace(
            id=user_id,
            username=f"user{user_id}",
            full_name=f"User {user_id}",
        ),
        callback_query=None,
        effective_message=message,
        effective_chat=SimpleNamespace(id=user_id),
    )


def _context(client: TaskApiClient) -> SimpleNamespace:
    return SimpleNamespace(
        application=SimpleNamespace(
            bot_data={SETTINGS_KEY: _settings(), TASK_API_CLIENT_KEY: client}
        ),
        bot=SimpleNamespace(send_message=AsyncMock()),
        args=[],
    )


class AccessGuardTest(unittest.IsolatedAsyncioTestCase):
    async def test_bootstraps_and_allows_admin(self) -> None:
        client = TaskApiClient(base_url="http://task-api.test")
        client.bootstrap_admin = AsyncMock(return_value={"status": "active"})
        context = _context(client)

        await access_guard_handler(_update(123456789), context)

        client.bootstrap_admin.assert_awaited_once()

    async def test_allows_active_user(self) -> None:
        client = TaskApiClient(base_url="http://task-api.test")
        client.get_current_user = AsyncMock(return_value={"status": "active"})

        await access_guard_handler(_update(7), _context(client))

    async def test_registers_new_user_notifies_admin_and_stops(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        client = TaskApiClient(base_url="http://task-api.test")
        client.get_current_user = AsyncMock(return_value=None)
        client.register_user = AsyncMock(
            return_value={"created": True, "user": {"status": "pending"}}
        )
        context = _context(client)

        with self.assertRaises(ApplicationHandlerStop):
            await access_guard_handler(_update(7, message), context)

        client.register_user.assert_awaited_once()
        context.bot.send_message.assert_awaited_once()
        message.reply_text.assert_awaited_once()


class AdminPanelTest(unittest.IsolatedAsyncioTestCase):
    async def test_admin_search_filters_users(self) -> None:
        client = TaskApiClient(base_url="http://task-api.test")
        client.list_users = AsyncMock(return_value=[
            {"telegramUserId": "123456789", "displayName": "Admin", "role": "admin", "status": "active"},
            {"telegramUserId": "7", "displayName": "Alice", "username": "alice", "role": "user", "status": "active"},
            {"telegramUserId": "8", "displayName": "Bob", "username": "bob", "role": "user", "status": "pending"},
        ])
        context = _context(client)
        context.args = ["alice"]

        await admin_handler(_update(123456789), context)

        sent = context.bot.send_message.await_args.kwargs
        labels = [button.text for row in sent["reply_markup"].inline_keyboard for button in row]
        self.assertTrue(any("Alice" in label for label in labels))
        self.assertFalse(any("Bob" in label for label in labels))

    async def test_delete_requires_two_confirmations(self) -> None:
        client = TaskApiClient(base_url="http://task-api.test")
        client.delete_user = AsyncMock()
        context = _context(client)
        query = SimpleNamespace(
            data="admin:ask:delete:7",
            from_user=SimpleNamespace(id=123456789),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query, effective_chat=SimpleNamespace(id=123456789))

        await admin_callback_handler(update, context)
        client.delete_user.assert_not_awaited()
        first_markup = query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertEqual(first_markup.inline_keyboard[0][0].callback_data, "admin:ask2:delete:7")

        query.data = "admin:ask2:delete:7"
        await admin_callback_handler(update, context)
        client.delete_user.assert_not_awaited()
        second_markup = query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertEqual(second_markup.inline_keyboard[0][0].callback_data, "admin:do:delete:7")

        query.data = "admin:do:delete:7"
        await admin_callback_handler(update, context)
        client.delete_user.assert_awaited_once_with(admin_user_id=123456789, user_id="7")
if __name__ == "__main__":
    unittest.main()